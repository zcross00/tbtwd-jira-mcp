# Project Instructions — The Brain That Wouldn't Die

## Vault-First Development Protocol

This workspace develops and uses the **tbtwd-obsidian** server — a persistent memory vault exposed via the Model Context Protocol. The vault is the authoritative source of design decisions, concepts, patterns, procedures, lessons, and project state across all projects.

**BLOCKING REQUIREMENT:** Before making any design decision, implementing any feature, or changing architecture, you MUST consult the vault. The vault contains accumulated project knowledge that supersedes assumptions.

## Session Start Protocol

1. **Always call `get_brief` first.** This returns the active project, goals, focus area, and backlog.
2. **Query for relevant context** — use `get_relevant_context(topic)` for one-shot aggregation, or `search`/`query`/`get_context` for targeted lookups.
3. **Load the component tree** — `query(entity_type="system", project="...")` to understand what exists in the active project.
4. **Cite vault sources** — reference entity titles (e.g., "per [[Work Implementation]]") when your actions are informed by vault knowledge.

## Context Recovery (After Compaction)

When context is compacted or summarized — conversation truncation, context window limits, session handoff:

1. Call `get_brief` immediately to re-establish orientation
2. Re-query vault entities that were actively informing your work via `get_relevant_context(topic)`
3. Re-read any files being edited — do not rely on compacted summaries
4. Re-load the component tree if implementation work is in progress

**Always prefer a fresh vault pull over a stale summary.**

## Procedures

The vault contains refined procedures for common workflows. **Before acting on any task, match it against the procedure list.** If no procedure matches but the task is multi-step, reusable, and repeatable, suggest creating a new procedure.

- **[[Work Implementation]]** — *triggers: implement, build, code, branch, commit, merge* — full lifecycle from task understanding to delivery
- **[[Work Verification]]** — *triggers: verify, validate, test, check quality* — compile gate → test gate → criteria verification → report
- **[[Work Planning]]** — *triggers: plan, scope, break down, prioritize, gap analysis* — goals → component tree → gap analysis → work items
- **[[Strategic Review]]** — *triggers: review, audit, health check, drift, retrospective* — drift detection, process improvements, phase assessment
- **[[Error Diagnosis]]** — *triggers: error, bug, fail, broken, crash, diagnose* — structured triage for compile, test, runtime, and tooling errors
- **[[Safe Refactoring]]** — *triggers: refactor, rename, restructure, move, migrate* — impact mapping → migration → verification gates
- **[[Design Synchronization]]** — *triggers: update design, sync design, architecture changed* — keeping component designs current after changes
- **[[Knowledge Cross-Pollination]]** — *triggers: enrich, cross-reference, connect, link entities* — enriching existing entities with information from other entities
- **[[Decision Management]]** — *triggers: decide, choose, trade-off, alternative, which approach* — recognizing, creating, surfacing, resolving, and reversing decision entities
- **[[Knowledge Curation]]** — *triggers: audit, curate, validate, check tags, maintenance, stale* — periodic vault audit: schema validation, tag coverage, status lifecycle, relationship integrity
- **[[Session Recovery]]** — *triggers: compact, resume, recover, handoff, continue, lost context* — re-establishing full context after compaction or session handoff

### Procedure Recognition

When the user directs you through a multi-step task that is reusable, repeatable, and non-trivial (3+ steps with meaningful decision points), and no existing procedure covers it — flag this to the user and suggest creating a procedure entity for it.

## Living Component Design

Per [[Living Component Design]], every project has a component tree of `system` entities. These describe actual architecture — what code exists and how it works. Update them after implementation. Split them when they grow complex. Create new ones for new systems.

## Decision Audit Trail

Follow [[Decision Management]] for the full lifecycle. Key points:

- **Search the vault first** for existing decisions, patterns, or lessons.
- **Never silently make a decision** — surface choices, alternatives, and recommendations to the user.
- **Cite the vault entity** if one exists: "Per [[Decision Title]], using approach X because..."
- **Flag gaps explicitly** if no vault precedent exists.
- After significant decisions, **persist new knowledge** via the synthesis pipeline.

## Knowledge Gathering (CRITICAL)

The vault must grow smarter with every session — this is a direct measure of how much you're learning. **Never skip an opportunity to capture useful knowledge.** Aggressively look for insights worth persisting throughout every task — not just at the end. Every insight persisted makes every future session faster and sharper.

Capture: debugging insights, architectural discoveries, process observations, user decisions, corrections to stale vault data, coding patterns observed in the codebase, efficiency shortcuts, cross-domain techniques, anti-patterns that waste time, anything a future session might need to know.

Persistence pipeline:
1. `get_extraction_schema` for the candidate format.
2. `list_tags` for the controlled vocabulary.
3. Extract candidates as atomic claims.
4. `match_concepts` to check for existing matches.
5. `synthesize` to persist.

Do not let knowledge evaporate. If something was learned, persist it. A session that produces no new knowledge is a session that failed to improve.

## Conflict Detection (CRITICAL)

When new information contradicts existing vault knowledge — from code, errors, user statements, or any source — you MUST flag it to the user immediately. Never silently accept or discard either side. The vault could be stale, or the new information could be wrong. State both sides, explain which seems more current and why, and let the user decide. After resolution, update the vault. This applies to ALL contradictions, no matter how minor.

**User input is high-authority.** Treat what the user says as important and likely correct, but always verify against the vault. Never ignore the user because the vault disagrees — and never ignore the vault because the user said something different. Surface every inconsistency, quote both sides, and let the user decide. Then update the vault. Recognizing inconsistencies is the single most valuable thing the agent can do for knowledge integrity.

## MCP Server Development

When modifying the MCP server code (`src/tbtwd_obsidian_mcp/`):
- The server is stateless — files are the source of truth, no shadow state
- Tools should return scoped, minimal context to stay within token budgets
- Search the vault for related `lesson` and `procedure` entities before debugging
- Check `drift` entities for known open questions before implementing uncertain features

## Vault Access Rule

Per [[Vault Access Via MCP Only]]: **never interact with vault files directly.** All reads go through MCP tools (`get_context`, `query`, `search`, etc.). All writes go through MCP tools (`update_memory`, `update_body`, `synthesize`, `archive_entity`). If the MCP server can't do what you need, enhance the server first, then use the new tool. Direct file manipulation bypasses validation, schema enforcement, and git management.

## Rule Enforcement (CRITICAL)

Vault `rule` entities are **enforceable constraints**, not suggestions. Violations are errors.

- `validate_action` automatically surfaces applicable rules — check `applicable_rules` in every response
- Before implementation, load active rules: `query(entity_type="rule", status="active")`
- When following a procedure, load its `## Applicable Rules` section via `get_context`
- **If a rule blocks your approach**, follow its prescribed alternative or escalation path — do NOT silently bypass it
- **Never acknowledge a rule and then ignore it** — that is worse than not knowing about the rule
- If no compliant path exists, flag it to the user and ask how to proceed
