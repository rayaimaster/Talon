"""
Jira integration tool.

Operates in three modes, controlled by environment variables:
  - JIRA_MODE=live    → real Jira REST API
  - JIRA_MODE=mock    → explicit mock mode for demos/testing
  - JIRA_MODE=disabled or unset with no Jira env vars → disabled
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def get_jira_mode() -> str:
    raw_mode = os.environ.get("JIRA_MODE", "").strip().lower()
    if raw_mode in {"disabled", "mock", "live"}:
        return raw_mode
    if raw_mode:
        logger.warning("Unknown JIRA_MODE=%r. Falling back to inferred mode.", raw_mode)

    if any(
        os.environ.get(key, "").strip()
        for key in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
    ):
        return "live"
    return "disabled"


def get_jira_status() -> str:
    mode = get_jira_mode()
    if mode == "disabled":
        return "disabled"
    if mode == "mock":
        return "mock"

    missing = _get_missing_live_config()
    if missing:
        return f"misconfigured ({', '.join(missing)})"
    return "configured"


def _get_missing_live_config() -> list[str]:
    missing: list[str] = []
    if not os.environ.get("JIRA_BASE_URL", "").strip():
        missing.append("JIRA_BASE_URL")
    if not os.environ.get("JIRA_EMAIL", "").strip():
        missing.append("JIRA_EMAIL")
    if not os.environ.get("JIRA_API_TOKEN", "").strip():
        missing.append("JIRA_API_TOKEN")
    return missing


def _disabled_message() -> str:
    return (
        "Jira integration is disabled. Set JIRA_MODE=live with JIRA_BASE_URL, "
        "JIRA_EMAIL, and JIRA_API_TOKEN to use real Jira, or set JIRA_MODE=mock "
        "for an explicit demo-only mode."
    )


def _misconfigured_message() -> str:
    missing = _get_missing_live_config()
    return (
        "❌ Jira integration is misconfigured for live mode. Missing: "
        f"{', '.join(missing)}. Set all required Jira env vars or switch to "
        "JIRA_MODE=mock for demo-only behavior."
    )


def _get_live_config() -> tuple[str, str, str] | None:
    if get_jira_mode() == "disabled":
        return None
    missing = _get_missing_live_config()
    if missing:
        return None
    return (
        os.environ["JIRA_BASE_URL"].rstrip("/"),
        os.environ["JIRA_EMAIL"].strip(),
        os.environ["JIRA_API_TOKEN"].strip(),
    )


async def _jira_request(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
) -> dict:
    config = _get_live_config()
    if config is None:
        raise RuntimeError(_misconfigured_message())

    base_url, email, api_token = config
    url = f"{base_url}{path}"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(
                method,
                url,
                params=params,
                json=json_body,
                auth=(email, api_token),
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300].strip() or exc.response.reason_phrase
        raise RuntimeError(
            f"Jira API request failed with {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Jira API request failed: {exc}") from exc


async def jira_get_issue(issue_key: str) -> str:
    """Fetch a Jira issue by key (e.g. 'ENG-123')."""
    mode = get_jira_mode()
    if mode == "disabled":
        return _disabled_message()
    if mode == "mock":
        return _mock_issue(issue_key)
    if _get_live_config() is None:
        return _misconfigured_message()

    if not issue_key.strip():
        return "❌ Jira issue key is required."

    try:
        data = await _jira_request("GET", f"/rest/api/3/issue/{issue_key.strip()}")

        fields = data.get("fields", {})
        return (
            f"Issue: {data.get('key')}\n"
            f"Summary: {fields.get('summary', 'N/A')}\n"
            f"Status: {fields.get('status', {}).get('name', 'N/A')}\n"
            f"Priority: {fields.get('priority', {}).get('name', 'N/A')}\n"
            f"Assignee: {(fields.get('assignee') or {}).get('displayName', 'Unassigned')}\n"
            f"Reporter: {(fields.get('reporter') or {}).get('displayName', 'N/A')}\n"
            f"Description: {_extract_description(fields.get('description'))}\n"
        )
    except RuntimeError as exc:
        logger.error("Jira get_issue failed: %s", exc)
        return f"❌ Failed to fetch Jira issue {issue_key}: {exc}"


async def jira_search(jql: str, max_results: int = 10) -> str:
    """Search Jira using JQL."""
    mode = get_jira_mode()
    if mode == "disabled":
        return _disabled_message()
    if mode == "mock":
        return _mock_search(jql, max_results)
    if _get_live_config() is None:
        return _misconfigured_message()

    if not jql.strip():
        return "❌ Jira search requires a non-empty JQL query."

    try:
        data = await _jira_request(
            "GET",
            "/rest/api/3/search",
            params={"jql": jql, "maxResults": max(1, min(int(max_results), 50))},
        )

        issues = data.get("issues", [])
        if not issues:
            return f"No issues found for JQL: {jql!r}"

        lines = [f"Found {len(issues)} issue(s) for: {jql!r}\n"]
        for issue in issues:
            fields = issue.get("fields", {})
            lines.append(
                f"  {issue.get('key')}: {fields.get('summary', 'N/A')} "
                f"[{fields.get('status', {}).get('name', '?')}]"
            )
        return "\n".join(lines)

    except RuntimeError as exc:
        logger.error("Jira search failed: %s", exc)
        return f"❌ Jira search failed: {exc}"


async def jira_create_issue(
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    priority: str = "Medium",
) -> str:
    """Create a new Jira issue."""
    mode = get_jira_mode()
    if mode == "disabled":
        return _disabled_message()
    if mode == "mock":
        import random
        ticket_num = random.randint(100, 9999)
        fake_key = f"{project_key}-{ticket_num}"
        return (
            f"✅ [MOCK] Created Jira issue: {fake_key}\n"
            f"  Summary: {summary}\n"
            f"  Type: {issue_type} | Priority: {priority}\n"
            f"  URL: https://your-company.atlassian.net/browse/{fake_key}"
        )
    if _get_live_config() is None:
        return _misconfigured_message()

    if not project_key.strip():
        return "❌ Jira project key is required."
    if not summary.strip():
        return "❌ Jira issue summary is required."

    base_url = os.environ["JIRA_BASE_URL"].rstrip("/")

    payload = {
        "fields": {
            "project": {"key": project_key.strip()},
            "summary": summary.strip(),
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            },
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
        }
    }

    try:
        data = await _jira_request(
            "POST",
            "/rest/api/3/issue",
            json_body=payload,
        )

        key = data.get("key", "?")
        return (
            f"✅ Created Jira issue: {key}\n"
            f"  URL: {base_url}/browse/{key}"
        )
    except RuntimeError as exc:
        logger.error("Jira create_issue failed: %s", exc)
        return f"❌ Failed to create Jira issue: {exc}"


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _mock_issue(key: str) -> str:
    return (
        f"[MOCK] Issue: {key}\n"
        f"Summary: Example issue for {key}\n"
        f"Status: In Progress\n"
        f"Priority: Medium\n"
        f"Assignee: Jane Smith\n"
        f"Reporter: John Doe\n"
        f"Description: This is a mock Jira issue. Set JIRA_BASE_URL to use real Jira.\n"
    )


def _mock_search(jql: str, max_results: int) -> str:
    return (
        f"[MOCK] Jira search results for: {jql!r}\n\n"
        f"  ENG-101: Fix login timeout issue [In Progress]\n"
        f"  ENG-102: Update SSL certificates [Done]\n"
        f"  ENG-103: Kubernetes pod restart loop [Open]\n\n"
        f"(Set JIRA_BASE_URL environment variable to use real Jira)"
    )


def _extract_description(desc: Optional[dict]) -> str:
    """Extract plain text from Atlassian Document Format."""
    if not desc:
        return "N/A"
    if isinstance(desc, str):
        return desc[:500]
    # ADF format
    try:
        parts = []
        for block in desc.get("content", []):
            for inline in block.get("content", []):
                if inline.get("type") == "text":
                    parts.append(inline.get("text", ""))
        return " ".join(parts)[:500]
    except Exception:
        return str(desc)[:200]
