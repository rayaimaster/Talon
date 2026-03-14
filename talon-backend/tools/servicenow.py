from __future__ import annotations

"""
ServiceNow ticket integration tool.

Operates in three modes, controlled by environment variables:
  - SERVICENOW_MODE=live    -> real ServiceNow Table API
  - SERVICENOW_MODE=mock    -> explicit mock mode for demos/testing
  - SERVICENOW_MODE=disabled or unset with no ServiceNow env vars -> disabled
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SERVICENOW_TABLE = "incident"


def get_servicenow_mode() -> str:
    raw_mode = os.environ.get("SERVICENOW_MODE", "").strip().lower()
    if raw_mode in {"disabled", "mock", "live"}:
        return raw_mode
    if raw_mode:
        logger.warning("Unknown SERVICENOW_MODE=%r. Falling back to inferred mode.", raw_mode)

    if any(
        os.environ.get(key, "").strip()
        for key in ("SERVICENOW_BASE_URL", "SERVICENOW_USERNAME", "SERVICENOW_PASSWORD")
    ):
        return "live"
    return "disabled"


def get_servicenow_status() -> str:
    mode = get_servicenow_mode()
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
    if not os.environ.get("SERVICENOW_BASE_URL", "").strip():
        missing.append("SERVICENOW_BASE_URL")
    if not os.environ.get("SERVICENOW_USERNAME", "").strip():
        missing.append("SERVICENOW_USERNAME")
    if not os.environ.get("SERVICENOW_PASSWORD", "").strip():
        missing.append("SERVICENOW_PASSWORD")
    return missing


def _disabled_message() -> str:
    return (
        "ServiceNow integration is disabled. Set SERVICENOW_MODE=live with "
        "SERVICENOW_BASE_URL, SERVICENOW_USERNAME, and SERVICENOW_PASSWORD to "
        "use real ServiceNow, or set SERVICENOW_MODE=mock for an explicit "
        "demo-only mode."
    )


def _misconfigured_message() -> str:
    missing = _get_missing_live_config()
    return (
        "❌ ServiceNow integration is misconfigured for live mode. Missing: "
        f"{', '.join(missing)}. Set all required ServiceNow env vars or switch "
        "to SERVICENOW_MODE=mock for demo-only behavior."
    )


def _resolve_table(table: str) -> str:
    resolved = table.strip() or os.environ.get("SERVICENOW_TABLE", DEFAULT_SERVICENOW_TABLE).strip()
    return resolved or DEFAULT_SERVICENOW_TABLE


def _get_live_config() -> Optional[tuple[str, str, str]]:
    if get_servicenow_mode() == "disabled":
        return None
    missing = _get_missing_live_config()
    if missing:
        return None
    return (
        os.environ["SERVICENOW_BASE_URL"].rstrip("/"),
        os.environ["SERVICENOW_USERNAME"].strip(),
        os.environ["SERVICENOW_PASSWORD"].strip(),
    )


async def _servicenow_request(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
) -> dict:
    config = _get_live_config()
    if config is None:
        raise RuntimeError(_misconfigured_message())

    base_url, username, password = config
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
                auth=(username, password),
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300].strip() or exc.response.reason_phrase
        raise RuntimeError(
            f"ServiceNow API request failed with {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"ServiceNow API request failed: {exc}") from exc


async def servicenow_get_ticket(ticket_number: str, table: str = "") -> str:
    """Fetch a ServiceNow ticket by number, e.g. INC0012345."""
    mode = get_servicenow_mode()
    resolved_table = _resolve_table(table)
    if mode == "disabled":
        return _disabled_message()
    if mode == "mock":
        return _mock_ticket(ticket_number, resolved_table)
    if _get_live_config() is None:
        return _misconfigured_message()
    if not ticket_number.strip():
        return "❌ ServiceNow ticket number is required."

    try:
        data = await _servicenow_request(
            "GET",
            f"/api/now/table/{resolved_table}",
            params={
                "sysparm_query": f"number={ticket_number.strip()}",
                "sysparm_limit": 1,
            },
        )
        results = data.get("result", [])
        if not results:
            return f"No ServiceNow ticket found for {ticket_number!r}"
        ticket = results[0]
        return (
            f"Ticket: {ticket.get('number', ticket_number)}\n"
            f"Table: {resolved_table}\n"
            f"Short Description: {ticket.get('short_description', 'N/A')}\n"
            f"State: {ticket.get('state', 'N/A')}\n"
            f"Priority: {ticket.get('priority', 'N/A')}\n"
            f"Urgency: {ticket.get('urgency', 'N/A')}\n"
            f"Caller: {(ticket.get('caller_id') or {}).get('display_value', ticket.get('caller_id', 'N/A'))}\n"
            f"Assigned To: {(ticket.get('assigned_to') or {}).get('display_value', ticket.get('assigned_to', 'Unassigned'))}\n"
            f"Description: {(ticket.get('description') or 'N/A')[:500]}\n"
        )
    except RuntimeError as exc:
        logger.error("ServiceNow get_ticket failed: %s", exc)
        return f"❌ Failed to fetch ServiceNow ticket {ticket_number}: {exc}"


async def servicenow_search_tickets(query: str, max_results: int = 10, table: str = "") -> str:
    """Search ServiceNow tickets using a ServiceNow sysparm_query string."""
    mode = get_servicenow_mode()
    resolved_table = _resolve_table(table)
    if mode == "disabled":
        return _disabled_message()
    if mode == "mock":
        return _mock_search(query, max_results, resolved_table)
    if _get_live_config() is None:
        return _misconfigured_message()
    if not query.strip():
        return "❌ ServiceNow search requires a non-empty query."

    try:
        data = await _servicenow_request(
            "GET",
            f"/api/now/table/{resolved_table}",
            params={
                "sysparm_query": query.strip(),
                "sysparm_limit": max(1, min(int(max_results), 50)),
            },
        )
        results = data.get("result", [])
        if not results:
            return f"No ServiceNow tickets found for query: {query!r}"

        lines = [f"Found {len(results)} ServiceNow ticket(s) for: {query!r}\n"]
        for ticket in results:
            lines.append(
                f"  {ticket.get('number', '?')}: {ticket.get('short_description', 'N/A')} "
                f"[state={ticket.get('state', '?')}]"
            )
        return "\n".join(lines)
    except RuntimeError as exc:
        logger.error("ServiceNow search failed: %s", exc)
        return f"❌ ServiceNow search failed: {exc}"


async def servicenow_create_ticket(
    short_description: str,
    description: str = "",
    urgency: str = "3",
    impact: str = "3",
    caller_id: str = "",
    table: str = "",
) -> str:
    """Create a ServiceNow ticket in the configured table."""
    mode = get_servicenow_mode()
    resolved_table = _resolve_table(table)
    if mode == "disabled":
        return _disabled_message()
    if mode == "mock":
        return (
            f"✅ [MOCK] Created ServiceNow ticket: INC0012345\n"
            f"  Table: {resolved_table}\n"
            f"  Short Description: {short_description}\n"
            f"  Urgency: {urgency} | Impact: {impact}\n"
            f"  URL: https://your-instance.service-now.com/nav_to.do?uri={resolved_table}.do?sys_id=mock"
        )
    if _get_live_config() is None:
        return _misconfigured_message()
    if not short_description.strip():
        return "❌ ServiceNow short description is required."

    payload = {
        "short_description": short_description.strip(),
        "description": description,
        "urgency": urgency,
        "impact": impact,
    }
    if caller_id.strip():
        payload["caller_id"] = caller_id.strip()

    try:
        data = await _servicenow_request(
            "POST",
            f"/api/now/table/{resolved_table}",
            json_body=payload,
        )
        ticket = data.get("result", {})
        base_url = os.environ["SERVICENOW_BASE_URL"].rstrip("/")
        return (
            f"✅ Created ServiceNow ticket: {ticket.get('number', '?')}\n"
            f"  Table: {resolved_table}\n"
            f"  URL: {base_url}/nav_to.do?uri={resolved_table}.do?sys_id={ticket.get('sys_id', '')}"
        )
    except RuntimeError as exc:
        logger.error("ServiceNow create_ticket failed: %s", exc)
        return f"❌ Failed to create ServiceNow ticket: {exc}"


def _mock_ticket(ticket_number: str, table: str) -> str:
    return (
        f"[MOCK] Ticket: {ticket_number}\n"
        f"Table: {table}\n"
        f"Short Description: Example ServiceNow ticket for {ticket_number}\n"
        f"State: 2\n"
        f"Priority: 3\n"
        f"Urgency: 3\n"
        f"Caller: Jane Employee\n"
        f"Assigned To: Dana Helpdesk\n"
        f"Description: This is a mock ServiceNow ticket. Set SERVICENOW_MODE=live to use real ServiceNow.\n"
    )


def _mock_search(query: str, max_results: int, table: str) -> str:
    return (
        f"[MOCK] ServiceNow search results for: {query!r} in table {table}\n\n"
        f"  INC0012345: VPN access broken for remote employee [state=2]\n"
        f"  INC0012346: Laptop encryption recovery request [state=1]\n"
        f"  INC0012347: Email client cannot send messages [state=3]\n\n"
        f"(Set SERVICENOW_MODE=live with ServiceNow credentials to use real tickets)"
    )
