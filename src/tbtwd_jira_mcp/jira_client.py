"""Async Jira Cloud REST API client."""

from __future__ import annotations

from base64 import b64encode

import httpx


class JiraError(Exception):
    """Raised when Jira API returns an error."""

    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"Jira API {status}: {message}")


class JiraClient:
    """Minimal async Jira Cloud REST API wrapper.

    Uses httpx for async HTTP with Basic auth (email:token).
    All methods return parsed JSON — response shaping happens in server.py.
    """

    def __init__(self, url: str, email: str, token: str):
        self._base = url.rstrip("/")
        auth = b64encode(f"{email}:{token}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict | list:
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msgs = body.get("errorMessages", [])
                errs = body.get("errors", {})
                parts = list(msgs) + [f"{k}: {v}" for k, v in errs.items()]
                msg = "; ".join(parts) if parts else resp.text
            except Exception:
                msg = resp.text
            raise JiraError(resp.status_code, msg)
        if resp.status_code == 204:
            return {}
        return resp.json()

    # --- Search & Issues ---

    async def search(
        self, jql: str, fields: list[str], max_results: int = 50
    ) -> dict:
        return await self._request(
            "POST",
            "/rest/api/3/search/jql",
            json={"jql": jql, "fields": fields, "maxResults": max_results},
        )

    async def get_issue(self, key: str, fields: list[str]) -> dict:
        field_str = ",".join(fields)
        return await self._request(
            "GET", f"/rest/api/3/issue/{key}", params={"fields": field_str}
        )

    async def create_issue(self, fields: dict) -> dict:
        return await self._request(
            "POST", "/rest/api/3/issue", json={"fields": fields}
        )

    async def update_issue(self, key: str, fields: dict) -> dict:
        return await self._request(
            "PUT", f"/rest/api/3/issue/{key}", json={"fields": fields}
        )

    # --- Transitions ---

    async def get_transitions(self, key: str) -> list[dict]:
        resp = await self._request(
            "GET", f"/rest/api/3/issue/{key}/transitions"
        )
        return resp.get("transitions", [])

    async def do_transition(self, key: str, transition_id: str) -> dict:
        return await self._request(
            "POST",
            f"/rest/api/3/issue/{key}/transitions",
            json={"transition": {"id": transition_id}},
        )

    # --- Issue Links ---

    async def create_issue_link(
        self, link_type: str, inward_key: str, outward_key: str
    ) -> dict:
        return await self._request(
            "POST",
            "/rest/api/3/issueLink",
            json={
                "type": {"name": link_type},
                "inwardIssue": {"key": inward_key},
                "outwardIssue": {"key": outward_key},
            },
        )

    # --- Metadata ---

    async def get_fields(self) -> list[dict]:
        return await self._request("GET", "/rest/api/3/field")

    async def get_issue_types(self) -> list[dict]:
        return await self._request("GET", "/rest/api/3/issuetype")

    async def get_priorities(self) -> list[dict]:
        return await self._request("GET", "/rest/api/3/priority")

    # --- Agile / Sprints ---

    async def get_boards(self, project_key: str) -> list[dict]:
        resp = await self._request(
            "GET",
            "/rest/agile/1.0/board",
            params={"projectKeyOrId": project_key},
        )
        return resp.get("values", [])

    async def get_active_sprint(self, board_id: int) -> dict | None:
        resp = await self._request(
            "GET",
            f"/rest/agile/1.0/board/{board_id}/sprint",
            params={"state": "active"},
        )
        sprints = resp.get("values", [])
        return sprints[0] if sprints else None

    async def close(self) -> None:
        if not self._client.is_closed:
            await self._client.aclose()
