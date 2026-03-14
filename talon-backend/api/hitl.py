"""
Human-in-the-loop request endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.admin_auth import require_admin_token
from channels.router import get_agent, get_all_agents
from core import audit, memory

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/hitl",
    tags=["hitl"],
    dependencies=[Depends(require_admin_token)],
)


class HitlCreateRequest(BaseModel):
    agent_id: str
    task: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    risk_level: str = Field(default="medium")
    requested_by: Optional[str] = None
    details: dict = Field(default_factory=dict)


class HitlDecisionRequest(BaseModel):
    note: Optional[str] = None
    decided_by: Optional[str] = None


def _serialize_request(request: dict, agent_name: str) -> dict:
    return {
        "id": request["id"],
        "agent_id": request["agent_id"],
        "agent_name": agent_name,
        "task": request["task"],
        "reason": request["reason"],
        "risk_level": request["risk_level"],
        "status": request["status"],
        "requested_by": request["requested_by"],
        "details": request["details"],
        "resolution_note": request["resolution_note"],
        "created_at": request["created_at"],
        "updated_at": request["updated_at"],
    }


@router.get("/requests")
async def get_hitl_requests(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    requests = await memory.list_hitl_requests(status=status, limit=limit)
    agents = get_all_agents()
    serialized = [
        _serialize_request(
            request,
            agents.get(request["agent_id"], {}).get("name", request["agent_id"]),
        )
        for request in requests
    ]
    return {
        "requests": serialized,
        "total": len(serialized),
    }


@router.post("/requests")
async def create_hitl_request(req: HitlCreateRequest) -> dict:
    config = get_agent(req.agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {req.agent_id!r} not found")

    request = await memory.create_hitl_request(
        agent_id=req.agent_id,
        task=req.task,
        reason=req.reason,
        risk_level=req.risk_level,
        requested_by=req.requested_by,
        details=req.details,
    )
    await audit.log_event(
        agent_id=req.agent_id,
        event_type="hitl_requested",
        user_id=req.requested_by,
        details={
            "request_id": request["id"],
            "task": req.task,
            "reason": req.reason,
            "risk_level": req.risk_level,
        },
    )
    logger.info("Created HITL request %s for %s", request["id"], req.agent_id)
    return _serialize_request(request, config.get("name", req.agent_id))


async def _update_request_status(
    request_id: int,
    status: str,
    req: HitlDecisionRequest,
) -> dict:
    existing = await memory.get_hitl_request(request_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"HITL request {request_id} not found")
    if existing["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"HITL request {request_id} is already in terminal state "
                f"{existing['status']!r}."
            ),
        )

    updated = await memory.update_hitl_request_status(
        request_id=request_id,
        status=status,
        resolution_note=req.note,
        expected_current_status="pending",
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"HITL request {request_id} not found")
    if updated["status"] != status:
        raise HTTPException(
            status_code=409,
            detail=(
                f"HITL request {request_id} could not transition to {status!r}. "
                f"Current state is {updated['status']!r}."
            ),
        )

    await audit.log_event(
        agent_id=updated["agent_id"],
        event_type=f"hitl_{status}",
        user_id=req.decided_by,
        details={
            "request_id": updated["id"],
            "task": updated["task"],
            "note": req.note,
        },
    )
    agent_config = get_agent(updated["agent_id"]) or {}
    agent_name = agent_config.get("name", updated["agent_id"])
    return _serialize_request(updated, agent_name)


@router.post("/requests/{request_id}/approve")
async def approve_hitl_request(request_id: int, req: HitlDecisionRequest) -> dict:
    return await _update_request_status(request_id, "approved", req)


@router.post("/requests/{request_id}/reject")
async def reject_hitl_request(request_id: int, req: HitlDecisionRequest) -> dict:
    return await _update_request_status(request_id, "rejected", req)
