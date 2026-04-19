"""Field mapping and configuration for Jira MCP server."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Brain vocabulary -> Jira custom field display names (for discovery)
CUSTOM_FIELD_NAMES: dict[str, str] = {
    "done_when": "Done When",
    "system_link": "System Link",
    "design_ref": "Design Ref",
}

# Brain issue type -> Jira issue type display name
ISSUE_TYPE_MAP: dict[str, str] = {
    "Feature": "Feature",
    "Bug": "Bug",
    "TechDebt": "Tech Debt",
    "Drift": "Drift",
    "Decision": "Decision",
}

# Jira issue type display name -> Brain vocabulary
ISSUE_TYPE_REVERSE: dict[str, str] = {v: k for k, v in ISSUE_TYPE_MAP.items()}

# Brain priority -> Jira priority name
PRIORITY_MAP: dict[str, str] = {
    "P1": "Highest",
    "P2": "High",
    "P3": "Medium",
    "P4": "Low",
}

# Jira priority name -> Brain vocabulary
PRIORITY_REVERSE: dict[str, str] = {v: k for k, v in PRIORITY_MAP.items()}

VALID_PRIORITIES = frozenset(PRIORITY_MAP.keys())
VALID_TYPES = frozenset(ISSUE_TYPE_MAP.keys())

CONFIG_FILE = "field_mapping.json"


@dataclass
class FieldConfig:
    """Discovered Jira field IDs for custom fields and type/priority caches."""

    done_when: str | None = None
    system_link: str | None = None
    design_ref: str | None = None
    issue_types: dict[str, str] = field(default_factory=dict)  # jira name -> id
    priorities: dict[str, str] = field(default_factory=dict)  # jira name -> id


def load_config(path: Path | None = None) -> FieldConfig | None:
    p = path or Path(CONFIG_FILE)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return FieldConfig(**data)


def save_config(config: FieldConfig, path: Path | None = None) -> None:
    p = path or Path(CONFIG_FILE)
    p.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
