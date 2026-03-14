"""
GitHub Issues integration tool.

Operates in three modes, controlled by environment variables:
  - GITHUB_MODE=live    -> real GitHub Issues REST API
  - GITHUB_MODE=mock    -> explicit mock mode for demos/testing
  - GITHUB_MODE=disabled or unset with no GitHub env vars -> disabled
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def get_github_mode() -> str:
    raw_mode = os.environ.get("GITHUB_MODE", "").strip().lower()
    if raw_mode in {"disabled", "mock", "live"}:
        return raw_mode
    if raw_mode:
        logger.warning("Unknown GITHUB_MODE=%r. Falling back to inferred mode.", raw_mode)

    if any(
        os.environ.get(key, "").strip()
        for key in ("GITHUB_TOKEN", "GITHUB_REPO")
    ):
        return "live"
    return "disabled"


def get_github_status() -> str:
    mode = get_github_mode()
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
    if not os.environ.get("GITHUB_TOKEN", "").strip():
        missing.append("GITHUB_TOKEN")
    if not os.environ.get("GITHUB_REPO", "").strip():
        missing.append("GITHUB_REPO")
    return missing


def _disabled_message() -> str:
    return (
        "GitHub Issues integration is disabled. Set GITHUB_MODE=live with "
        "GITHUB_TOKEN and GITHUB_REPO to use real GitHub Issues, or set "
        "GITHUB_MODE=mock for an explicit demo-only mode."
    )


def _misconfigured_message() -> str:
    missing = _get_missing_live_config()
    return (
        "❌ GitHub Issues integration is misconfigured for live mode. Missing: "
        f"{', '.join(missing)}. Set all required GitHub env vars or switch to "
        "GITHUB_MODE=mock for demo-only behavior."
    )


def _get_default_repo() -> str:
    return os.environ.get("GITHUB_REPO", "").strip()


def _resolve_repo(repo: Optional[str]) -> str:
    resolved = (repo or "").strip() or _get_default_repo()
    if not resolved:
        raise RuntimeError(
            "GitHub Issues requires a repository in owner/repo format. "
            "Set GITHUB_REPO or pass repo explicitly."
        )
    if "/" not in resolved:
        raise RuntimeError(
            f"Invalid GitHub repository {resolved!r}. Expected owner/repo format."
        )
    return resolved


def _get_live_config() -> tuple[str, str] | None:
    if get_github_mode() == "disabled":
        return None
    missing = _get_missing_live_config()
    if missing:
        return None
    return (
        os.environ["GITHUB_TOKEN"].strip(),
        os.environ["GITHUB_REPO"].strip(),
    )


async def _github_request(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
) -> dict:
    config = _get_live_config()
    if config is None:
        raise RuntimeError(_misconfigured_message())

    token, _default_repo = config
    url = f"https://api.github.com{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
            )
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300].strip() or exc.response.reason_phrase
        raise RuntimeError(
            f"GitHub API request failed with {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"GitHub API request failed: {exc}") from exc


async def github_get_issue(issue_number: int, repo: str = "") -> str:
    """Fetch a GitHub issue by number."""
    mode = get_github_mode()
    if mode == "disabled":
        return _disabled_message()
    if mode == "mock":
        return _mock_issue(issue_number, repo or _get_default_repo() or "example/repo")
    if _get_live_config() is None:
        return _misconfigured_message()
    if int(issue_number) <= 0:
        return "❌ GitHub issue number must be a positive integer."

    try:
        resolved_repo = _resolve_repo(repo)
        data = await _github_request(
            "GET",
            f"/repos/{resolved_repo}/issues/{int(issue_number)}",
        )
        return (
            f"Issue: {resolved_repo}#{data.get('number')}\n"
            f"Title: {data.get('title', 'N/A')}\n"
            f"State: {data.get('state', 'N/A')}\n"
            f"Author: {(data.get('user') or {}).get('login', 'N/A')}\n"
            f"Assignees: {', '.join(user.get('login', '') for user in data.get('assignees', [])) or 'Unassigned'}\n"
            f"Labels: {', '.join(label.get('name', '') for label in data.get('labels', [])) or 'None'}\n"
            f"URL: {data.get('html_url', 'N/A')}\n"
            f"Body: {(data.get('body') or 'N/A')[:500]}\n"
        )
    except RuntimeError as exc:
        logger.error("GitHub get_issue failed: %s", exc)
        return f"❌ Failed to fetch GitHub issue #{issue_number}: {exc}"


async def github_search_issues(query: str, max_results: int = 10, repo: str = "") -> str:
    """Search GitHub issues using GitHub issue search syntax."""
    mode = get_github_mode()
    if mode == "disabled":
        return _disabled_message()
    if mode == "mock":
        return _mock_search(query, max_results, repo or _get_default_repo() or "example/repo")
    if _get_live_config() is None:
        return _misconfigured_message()
    if not query.strip():
        return "❌ GitHub issue search requires a non-empty query."

    try:
        resolved_repo = _resolve_repo(repo)
        full_query = query.strip()
        if f"repo:{resolved_repo}" not in full_query:
            full_query = f"repo:{resolved_repo} is:issue {full_query}"

        data = await _github_request(
            "GET",
            "/search/issues",
            params={
                "q": full_query,
                "per_page": max(1, min(int(max_results), 50)),
            },
        )
        items = data.get("items", [])
        if not items:
            return f"No GitHub issues found for query: {query!r}"

        lines = [f"Found {len(items)} GitHub issue(s) for: {query!r}\n"]
        for item in items:
            lines.append(
                f"  {item.get('repository_url', '').split('/repos/')[-1]}#{item.get('number')}: "
                f"{item.get('title', 'N/A')} [{item.get('state', '?')}]"
            )
        return "\n".join(lines)
    except RuntimeError as exc:
        logger.error("GitHub issue search failed: %s", exc)
        return f"❌ GitHub issue search failed: {exc}"


async def github_create_issue(
    title: str,
    body: str = "",
    labels: Optional[list[str]] = None,
    repo: str = "",
) -> str:
    """Create a new GitHub issue."""
    mode = get_github_mode()
    if mode == "disabled":
        return _disabled_message()
    if mode == "mock":
        mock_repo = repo or _get_default_repo() or "example/repo"
        return (
            f"✅ [MOCK] Created GitHub issue: {mock_repo}#321\n"
            f"  Title: {title}\n"
            f"  Labels: {', '.join(labels or []) or 'None'}\n"
            f"  URL: https://github.com/{mock_repo}/issues/321"
        )
    if _get_live_config() is None:
        return _misconfigured_message()
    if not title.strip():
        return "❌ GitHub issue title is required."

    try:
        resolved_repo = _resolve_repo(repo)
        data = await _github_request(
            "POST",
            f"/repos/{resolved_repo}/issues",
            json_body={
                "title": title.strip(),
                "body": body,
                "labels": labels or [],
            },
        )
        return (
            f"✅ Created GitHub issue: {resolved_repo}#{data.get('number', '?')}\n"
            f"  URL: {data.get('html_url', f'https://github.com/{resolved_repo}/issues')}"
        )
    except RuntimeError as exc:
        logger.error("GitHub create_issue failed: %s", exc)
        return f"❌ Failed to create GitHub issue: {exc}"


def _mock_issue(issue_number: int, repo: str) -> str:
    return (
        f"[MOCK] Issue: {repo}#{issue_number}\n"
        f"Title: Example issue for #{issue_number}\n"
        f"State: open\n"
        f"Author: octocat\n"
        f"Assignees: teammate\n"
        f"Labels: bug, triage\n"
        f"URL: https://github.com/{repo}/issues/{issue_number}\n"
        f"Body: This is a mock GitHub issue. Set GITHUB_MODE=live to use real GitHub Issues.\n"
    )


def _mock_search(query: str, max_results: int, repo: str) -> str:
    return (
        f"[MOCK] GitHub issue search results for: {query!r} in {repo}\n\n"
        f"  {repo}#101: Fix flaky CI pipeline [open]\n"
        f"  {repo}#102: Improve audit export flow [open]\n"
        f"  {repo}#103: Add better operator metrics [closed]\n\n"
        f"(Set GITHUB_MODE=live with GITHUB_TOKEN and GITHUB_REPO to use real GitHub Issues)"
    )
