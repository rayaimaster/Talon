from __future__ import annotations

"""
System-wide control endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.admin_auth import require_admin_token
from core import audit, memory

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/system",
    tags=["system-control"],
    dependencies=[Depends(require_admin_token)],
)


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = ""
    updated_by: Optional[str] = None


@router.get("/kill-switch")
async def get_kill_switch() -> dict:
    return {"kill_switch": await memory.get_kill_switch_state()}


@router.post("/kill-switch")
async def set_kill_switch(req: KillSwitchRequest) -> dict:
    state = await memory.set_kill_switch_state(
        active=req.active,
        reason=req.reason,
        updated_by=req.updated_by,
    )
    await audit.log_event(
        agent_id="system",
        event_type="kill_switch_activated" if req.active else "kill_switch_deactivated",
        user_id=req.updated_by,
        details={"reason": req.reason},
    )
    logger.warning(
        "Global kill switch %s by %s",
        "activated" if req.active else "deactivated",
        req.updated_by or "unknown",
    )
    return {"kill_switch": state}
