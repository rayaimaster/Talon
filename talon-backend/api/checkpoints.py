"""
Agent checkpoint and rollback endpoints.
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
    prefix="/api/checkpoints",
    tags=["checkpoints"],
    dependencies=[Depends(require_admin_token)],
)


class CheckpointCreateRequest(BaseModel):
    agent_id: str
    label: str = Field(min_length=1)
    summary: str = ""
    created_by: Optional[str] = None


class CheckpointRestoreRequest(BaseModel):
    created_by: Optional[str] = None
    create_safety_checkpoint: bool = True


def _serialize_checkpoint(checkpoint: dict, agent_name: str) -> dict:
    snapshot = checkpoint.get("snapshot", {})
    return {
        "id": checkpoint["id"],
        "agent_id": checkpoint["agent_id"],
        "agent_name": agent_name,
        "label": checkpoint["label"],
        "summary": checkpoint["summary"],
        "created_by": checkpoint.get("created_by"),
        "created_at": checkpoint["created_at"],
        "stats": {
            "conversations": len(snapshot.get("conversations", [])),
            "episodic_memories": len(snapshot.get("episodic_memory", [])),
            "entity_records": len(snapshot.get("entity_memory", [])),
            "hitl_requests": len(snapshot.get("hitl_requests", [])),
            "scheduled_jobs": len(snapshot.get("scheduled_jobs", [])),
        },
    }


@router.get("")
async def list_checkpoints(
    agent_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    checkpoints = await memory.list_agent_checkpoints(agent_id=agent_id, limit=limit)
    agents = get_all_agents()
    return {
        "checkpoints": [
            _serialize_checkpoint(
                checkpoint,
                agents.get(checkpoint["agent_id"], {}).get("name", checkpoint["agent_id"]),
            )
            for checkpoint in checkpoints
        ],
        "total": len(checkpoints),
    }


@router.post("")
async def create_checkpoint(req: CheckpointCreateRequest) -> dict:
    config = get_agent(req.agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {req.agent_id!r} not found")

    checkpoint = await memory.create_agent_checkpoint(
        agent_id=req.agent_id,
        label=req.label,
        summary=req.summary,
        created_by=req.created_by,
    )
    await audit.log_event(
        agent_id=req.agent_id,
        event_type="checkpoint_created",
        user_id=req.created_by,
        details={
            "checkpoint_id": checkpoint["id"],
            "label": req.label,
            "summary": req.summary,
        },
    )
    return {"checkpoint": _serialize_checkpoint(checkpoint, config.get("name", req.agent_id))}


@router.post("/{checkpoint_id}/restore")
async def restore_checkpoint(checkpoint_id: int, req: CheckpointRestoreRequest) -> dict:
    checkpoint = await memory.get_agent_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")

    try:
        result = await memory.restore_agent_checkpoint(
            checkpoint_id=checkpoint_id,
            create_safety_checkpoint=req.create_safety_checkpoint,
            created_by=req.created_by,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    agent_name = get_all_agents().get(checkpoint["agent_id"], {}).get("name", checkpoint["agent_id"])
    await audit.log_event(
        agent_id=checkpoint["agent_id"],
        event_type="checkpoint_restored",
        user_id=req.created_by,
        details={
            "checkpoint_id": checkpoint_id,
            "label": checkpoint["label"],
            "safety_checkpoint_id": result["safety_checkpoint"]["id"] if result["safety_checkpoint"] else None,
        },
    )

    return {
        "checkpoint": _serialize_checkpoint(result["checkpoint"], agent_name),
        "safety_checkpoint": (
            _serialize_checkpoint(result["safety_checkpoint"], agent_name)
            if result["safety_checkpoint"]
            else None
        ),
    }
