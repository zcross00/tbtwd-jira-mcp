"""Jira MCP server — token-efficient backlog access for TBTWD agents."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from .config import (
    CUSTOM_FIELD_NAMES,
    ISSUE_TYPE_MAP,
    ISSUE_TYPE_REVERSE,
    PRIORITY_MAP,
    PRIORITY_REVERSE,
    VALID_PRIORITIES,
    VALID_TYPES,
    FieldConfig,
    load_config,
    save_config,
)
from .jira_client import JiraClient, JiraError

mcp = FastMCP(
    "tbtwd-jira-mcp",
    instructions="Token-efficient Jira backlog access for TBTWD agents",
)

_client: JiraClient | None = None
_config: FieldConfig | None = None


def _get_client() -> JiraClient:
    global _client
    if _client is None:
        url = os.environ.get("JIRA_URL", "")
        email = os.environ.get("JIRA_EMAIL", "")
        token = os.environ.get("JIRA_API_TOKEN", "")
        if not all([url, email, token]):
            raise ValueError(
                "Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN env vars"
            )
        _client = JiraClient(url, email, token)
    return _client


def _get_config() -> FieldConfig | None:
    global _config
    if _config is None:
        _config = load_config()
    return _config


# ---------------------------------------------------------------------------
# Response shaping — the core token-efficiency win
# ---------------------------------------------------------------------------


def _adf_to_text(node: dict | None) -> str:
    """Extract plain text from Atlassian Document Format."""
    if not node or not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    children = node.get("content", [])
    if node.get("type") in ("paragraph", "heading", "listItem"):
        return "".join(_adf_to_text(c) for c in children)
    return "\n".join(filter(None, (_adf_to_text(c) for c in children)))


def _text_to_adf(text: str) -> dict:
    """Wrap plain text in minimal ADF structure."""
    if not text:
        return {"version": 1, "type": "doc", "content": []}
    paras = []
    for line in text.split("\n"):
        if line.strip():
            paras.append(
                {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            )
    if not paras:
        paras.append(
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        )
    return {"version": 1, "type": "doc", "content": paras}


def _extract_blockers(links: list[dict]) -> list[str]:
    """Extract blocker keys from Jira issue links."""
    blockers = []
    for link in links:
        if (
            link.get("type", {}).get("inward") == "is blocked by"
            and "inwardIssue" in link
        ):
            blockers.append(link["inwardIssue"]["key"])
    return blockers


def _shape_synopsis(issue: dict, config: FieldConfig | None) -> dict:
    """Minimal shape for list views — ~30 tokens per item."""
    f = issue.get("fields", {})
    type_name = f.get("issuetype", {}).get("name", "")
    pri_name = f.get("priority", {}).get("name", "")
    return {
        k: v
        for k, v in {
            "key": issue["key"],
            "type": ISSUE_TYPE_REVERSE.get(type_name, type_name),
            "synopsis": f.get("summary", ""),
            "priority": PRIORITY_REVERSE.get(pri_name, pri_name),
            "status": f.get("status", {}).get("name", ""),
        }.items()
        if v
    }


def _shape_item(issue: dict, config: FieldConfig | None) -> dict:
    """Full shape for single-item view — ~80-150 tokens."""
    f = issue.get("fields", {})
    type_name = f.get("issuetype", {}).get("name", "")
    pri_name = f.get("priority", {}).get("name", "")

    shaped: dict = {
        "key": issue["key"],
        "type": ISSUE_TYPE_REVERSE.get(type_name, type_name),
        "synopsis": f.get("summary", ""),
        "priority": PRIORITY_REVERSE.get(pri_name, pri_name),
        "status": f.get("status", {}).get("name", ""),
    }

    if config:
        if config.system_link and f.get(config.system_link):
            shaped["system"] = f[config.system_link]
        if config.done_when and f.get(config.done_when):
            shaped["done_when"] = f[config.done_when]
        if config.design_ref and f.get(config.design_ref):
            shaped["design_ref"] = f[config.design_ref]

    desc = _adf_to_text(f.get("description"))
    if desc:
        shaped["detail"] = desc

    blockers = _extract_blockers(f.get("issuelinks", []))
    if blockers:
        shaped["blocked_by"] = blockers

    return {k: v for k, v in shaped.items() if v}


# ---------------------------------------------------------------------------
# JQL builder
# ---------------------------------------------------------------------------


def _build_jql(
    project: str,
    *,
    priority: str | None = None,
    status: str | None = None,
    item_type: str | None = None,
    system: str | None = None,
    text: str | None = None,
    sprint: str | None = None,
    config: FieldConfig | None = None,
) -> str:
    clauses = [f'project = "{project}"']
    if priority:
        jira_pri = PRIORITY_MAP.get(priority, priority)
        clauses.append(f'priority = "{jira_pri}"')
    if status:
        clauses.append(f'status = "{status}"')
    if item_type:
        jira_type = ISSUE_TYPE_MAP.get(item_type, item_type)
        clauses.append(f'issuetype = "{jira_type}"')
    if system and config and config.system_link:
        clauses.append(f'cf[{config.system_link.replace("customfield_", "")}] ~ "{system}"')
    if text:
        clauses.append(f'text ~ "{text}"')
    if sprint and sprint.lower() == "current":
        clauses.append("sprint in openSprints()")
    return " AND ".join(clauses) + " ORDER BY priority ASC, created DESC"


# ---------------------------------------------------------------------------
# Field lists — request only what we need from Jira
# ---------------------------------------------------------------------------


def _base_fields(config: FieldConfig | None) -> list[str]:
    fields = ["summary", "issuetype", "priority", "status"]
    if config and config.system_link:
        fields.append(config.system_link)
    return fields


def _detail_fields(config: FieldConfig | None) -> list[str]:
    fields = _base_fields(config) + ["description", "issuelinks"]
    if config:
        if config.done_when:
            fields.append(config.done_when)
        if config.design_ref:
            fields.append(config.design_ref)
    return fields


# ---------------------------------------------------------------------------
# Compact JSON helper
# ---------------------------------------------------------------------------

_json = lambda obj: json.dumps(obj, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def discover_fields(project: str) -> str:
    """Discover Jira field IDs, issue types, and priorities. Run once after
    creating custom fields, or to refresh the mapping. Returns what was found
    and what needs to be created.

    Args:
        project: Jira project key (e.g. "SOV")
    """
    client = _get_client()
    config = FieldConfig()
    report: dict = {"custom_fields": {}, "missing_fields": [], "types": {}, "missing_types": [], "priorities": {}}

    # Custom fields
    all_fields = await client.get_fields()
    name_to_id = {f["name"]: f["id"] for f in all_fields if f.get("custom")}
    for brain_key, display_name in CUSTOM_FIELD_NAMES.items():
        fid = name_to_id.get(display_name)
        if fid:
            setattr(config, brain_key, fid)
            report["custom_fields"][brain_key] = fid
        else:
            report["missing_fields"].append(display_name)

    # Issue types
    all_types = await client.get_issue_types()
    available = {t["name"]: t["id"] for t in all_types if not t.get("subtask")}
    config.issue_types = available
    expected = set(ISSUE_TYPE_MAP.values())
    report["types"] = {k: v for k, v in available.items() if k in expected}
    report["missing_types"] = sorted(expected - set(available.keys()))

    # Priorities
    all_pris = await client.get_priorities()
    for p in all_pris:
        config.priorities[p["name"]] = p["id"]
    report["priorities"] = {
        brain: config.priorities.get(jira, "?")
        for brain, jira in PRIORITY_MAP.items()
        if jira in config.priorities
    }

    save_config(config)
    global _config
    _config = config

    # Strip empty lists for compactness
    return _json({k: v for k, v in report.items() if v})


@mcp.tool()
async def list_backlog(
    project: str,
    priority: str | None = None,
    status: str | None = None,
    item_type: str | None = None,
    system: str | None = None,
    text: str | None = None,
    sprint: str | None = None,
) -> str:
    """List backlog items with optional filters. Returns synopses only.

    Args:
        project: Jira project key (e.g. "SOV")
        priority: P1-P4
        status: "To Do", "In Progress", or "Done"
        item_type: Feature, Bug, TechDebt, Drift, or Decision
        system: Vault system entity name to filter by
        text: Full-text search
        sprint: "current" for active sprint items
    """
    client = _get_client()
    config = _get_config()
    jql = _build_jql(
        project,
        priority=priority,
        status=status,
        item_type=item_type,
        system=system,
        text=text,
        sprint=sprint,
        config=config,
    )
    result = await client.search(jql, _base_fields(config), max_results=50)
    items = [_shape_synopsis(i, config) for i in result.get("issues", [])]
    return _json({"items": items, "total": result.get("total", 0)})


@mcp.tool()
async def get_backlog_item(key: str) -> str:
    """Get full detail for one backlog item.

    Args:
        key: Jira issue key (e.g. "SOV-42")
    """
    client = _get_client()
    config = _get_config()
    issue = await client.get_issue(key, _detail_fields(config))
    return _json(_shape_item(issue, config))


@mcp.tool()
async def create_backlog_item(
    project: str,
    synopsis: str,
    priority: str,
    item_type: str,
    done_when: str | None = None,
    system: str | None = None,
    design_ref: str | None = None,
    detail: str | None = None,
    blocked_by: list[str] | None = None,
) -> str:
    """Create a backlog item.

    Args:
        project: Jira project key (e.g. "SOV")
        synopsis: One-line summary
        priority: P1-P4
        item_type: Feature, Bug, TechDebt, Drift, or Decision
        done_when: Acceptance criteria (1-2 sentences)
        system: Vault system entity name
        design_ref: Vault entity reference (e.g. "[[Job Assignment]]")
        detail: Extended description
        blocked_by: List of issue keys this is blocked by
    """
    if priority not in VALID_PRIORITIES:
        return _json({"error": f"Invalid priority '{priority}'. Use P1-P4."})
    if item_type not in VALID_TYPES:
        return _json({"error": f"Invalid type '{item_type}'. Use: {', '.join(sorted(VALID_TYPES))}"})

    client = _get_client()
    config = _get_config()

    jira_type = ISSUE_TYPE_MAP[item_type]
    jira_priority = PRIORITY_MAP[priority]

    fields: dict = {
        "project": {"key": project},
        "summary": synopsis,
    }

    # Use IDs when available (more reliable), fall back to names
    if config and jira_type in config.issue_types:
        fields["issuetype"] = {"id": config.issue_types[jira_type]}
    else:
        fields["issuetype"] = {"name": jira_type}

    if config and jira_priority in config.priorities:
        fields["priority"] = {"id": config.priorities[jira_priority]}
    else:
        fields["priority"] = {"name": jira_priority}

    if detail:
        fields["description"] = _text_to_adf(detail)
    if config:
        if done_when and config.done_when:
            fields[config.done_when] = done_when
        if system and config.system_link:
            fields[config.system_link] = system
        if design_ref and config.design_ref:
            fields[config.design_ref] = design_ref

    result = await client.create_issue(fields)
    new_key = result.get("key", "")

    if blocked_by and new_key:
        for blocker_key in blocked_by:
            try:
                await client.create_issue_link("Blocks", blocker_key, new_key)
            except JiraError:
                pass  # Non-fatal: item created, link failed

    return _json({"key": new_key})


@mcp.tool()
async def update_backlog_item(key: str, fields: dict) -> str:
    """Update fields on a backlog item. Only send changed fields.

    Args:
        key: Jira issue key (e.g. "SOV-42")
        fields: Dict of Brain-vocabulary fields to update. Valid keys:
                synopsis, priority, item_type, done_when, system, design_ref, detail
    """
    client = _get_client()
    config = _get_config()
    jira_fields: dict = {}

    if "synopsis" in fields:
        jira_fields["summary"] = fields["synopsis"]
    if "priority" in fields:
        pri = fields["priority"]
        jira_pri = PRIORITY_MAP.get(pri, pri)
        if config and jira_pri in config.priorities:
            jira_fields["priority"] = {"id": config.priorities[jira_pri]}
        else:
            jira_fields["priority"] = {"name": jira_pri}
    if "item_type" in fields:
        t = fields["item_type"]
        jira_t = ISSUE_TYPE_MAP.get(t, t)
        if config and jira_t in config.issue_types:
            jira_fields["issuetype"] = {"id": config.issue_types[jira_t]}
        else:
            jira_fields["issuetype"] = {"name": jira_t}
    if "detail" in fields:
        jira_fields["description"] = _text_to_adf(fields["detail"])
    if config:
        if "done_when" in fields and config.done_when:
            jira_fields[config.done_when] = fields["done_when"]
        if "system" in fields and config.system_link:
            jira_fields[config.system_link] = fields["system"]
        if "design_ref" in fields and config.design_ref:
            jira_fields[config.design_ref] = fields["design_ref"]

    if not jira_fields:
        return _json({"error": "No valid fields to update"})

    await client.update_issue(key, jira_fields)
    return _json({"updated": key})


@mcp.tool()
async def transition_item(key: str, status: str) -> str:
    """Move a backlog item to a new workflow status.

    Args:
        key: Jira issue key (e.g. "SOV-42")
        status: Target status — "To Do", "In Progress", or "Done"
    """
    client = _get_client()
    transitions = await client.get_transitions(key)

    target = None
    for t in transitions:
        if t.get("to", {}).get("name", "").lower() == status.lower():
            target = t
            break

    if not target:
        available = [t.get("to", {}).get("name", "") for t in transitions]
        return _json({"error": f"No transition to '{status}'", "available": available})

    await client.do_transition(key, target["id"])
    return _json({"transitioned": key, "status": status})


@mcp.tool()
async def get_sprint_context(project: str) -> str:
    """Current sprint overview — name, goal, dates, progress, and item list.

    Args:
        project: Jira project key (e.g. "SOV")
    """
    client = _get_client()
    config = _get_config()

    boards = await client.get_boards(project)
    if not boards:
        return _json({"error": "No board found for project"})

    sprint = await client.get_active_sprint(boards[0]["id"])
    if not sprint:
        return _json({"sprint": None, "message": "No active sprint"})

    jql = f'project = "{project}" AND sprint = {sprint["id"]} ORDER BY priority ASC'
    result = await client.search(jql, _base_fields(config), max_results=50)

    progress: dict[str, int] = {}
    items = []
    for issue in result.get("issues", []):
        shaped = _shape_synopsis(issue, config)
        items.append(shaped)
        st = shaped.get("status", "Unknown")
        progress[st] = progress.get(st, 0) + 1

    ctx = {
        "sprint": sprint.get("name", ""),
        "goal": sprint.get("goal", ""),
        "start": (sprint.get("startDate") or "")[:10] or None,
        "end": (sprint.get("endDate") or "")[:10] or None,
        "progress": progress,
        "items": items,
    }
    return _json({k: v for k, v in ctx.items() if v})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
