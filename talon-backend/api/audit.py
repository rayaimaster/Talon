"""
Audit trail REST endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.admin_auth import require_admin_token
from core import audit

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
    dependencies=[Depends(require_admin_token)],
)


@router.get("/events")
async def get_audit_events(
    agent_id: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """
    Retrieve audit events with optional filtering.

    Query params:
      - agent_id:   filter to a specific agent
      - event_type: filter by event type (message_received, tool_called, etc.)
      - limit:      max events to return (default 100, max 500)
      - offset:     pagination offset
    """
    events = await audit.get_events(
        agent_id=agent_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    total = await audit.count_events(agent_id=agent_id)
    return {
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
