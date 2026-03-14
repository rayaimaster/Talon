"""
Scheduled job management endpoints.
"""

import time
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.admin_auth import require_admin_token
from channels.router import get_agent, get_all_agents
from core import audit, memory

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/schedules",
    tags=["schedules"],
    dependencies=[Depends(require_admin_token)],
)


class ScheduleCreateRequest(BaseModel):
    agent_id: str
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    interval_minutes: int = Field(ge=1, le=24 * 60)
    start_immediately: bool = False


def _serialize_job(job: dict, agent_name: str) -> dict:
    return {
        "id": job["id"],
        "agent_id": job["agent_id"],
        "agent_name": agent_name,
        "name": job["name"],
        "prompt": job["prompt"],
        "interval_minutes": job["interval_minutes"],
        "status": job["status"],
        "last_run_at": job["last_run_at"],
        "next_run_at": job["next_run_at"],
        "last_result": job["last_result"],
        "last_error": job["last_error"],
        "last_conversation_id": job["last_conversation_id"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


@router.get("/jobs")
async def get_scheduled_jobs(agent_id: Optional[str] = Query(default=None)) -> dict:
    jobs = await memory.list_scheduled_jobs(agent_id=agent_id)
    agents = get_all_agents()
    return {
        "jobs": [
            _serialize_job(job, agents.get(job["agent_id"], {}).get("name", job["agent_id"]))
            for job in jobs
        ],
        "total": len(jobs),
    }


@router.post("/jobs")
async def create_scheduled_job(req: ScheduleCreateRequest) -> dict:
    config = get_agent(req.agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {req.agent_id!r} not found")

    job = await memory.create_scheduled_job(
        agent_id=req.agent_id,
        name=req.name,
        prompt=req.prompt,
        interval_minutes=req.interval_minutes,
        start_immediately=req.start_immediately,
    )
    await audit.log_event(
        agent_id=req.agent_id,
        event_type="scheduled_job_created",
        details={
            "job_id": job["id"],
            "job_name": req.name,
            "interval_minutes": req.interval_minutes,
        },
    )
    return {"job": _serialize_job(job, config.get("name", req.agent_id))}


async def _get_job_or_404(job_id: int) -> dict:
    job = await memory.get_scheduled_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Scheduled job {job_id} not found")
    return job


@router.post("/jobs/{job_id}/pause")
async def pause_scheduled_job(job_id: int) -> dict:
    job = await _get_job_or_404(job_id)
    updated = await memory.set_scheduled_job_status(job_id, "paused")
    await audit.log_event(
        agent_id=job["agent_id"],
        event_type="scheduled_job_paused",
        details={"job_id": job_id, "job_name": job["name"]},
    )
    agent_name = get_all_agents().get(job["agent_id"], {}).get("name", job["agent_id"])
    return {"job": _serialize_job(updated, agent_name)}


@router.post("/jobs/{job_id}/resume")
async def resume_scheduled_job(job_id: int) -> dict:
    job = await _get_job_or_404(job_id)
    updated = await memory.set_scheduled_job_status(job_id, "active")
    if updated and updated["next_run_at"] and updated["next_run_at"] < time.time():
        updated = await memory.touch_scheduled_job_next_run(job_id, time.time())
    await audit.log_event(
        agent_id=job["agent_id"],
        event_type="scheduled_job_resumed",
        details={"job_id": job_id, "job_name": job["name"]},
    )
    agent_name = get_all_agents().get(job["agent_id"], {}).get("name", job["agent_id"])
    return {"job": _serialize_job(updated, agent_name)}


@router.post("/jobs/{job_id}/run")
async def run_scheduled_job_now(job_id: int) -> dict:
    job = await _get_job_or_404(job_id)
    updated = await memory.set_scheduled_job_status(job_id, "active")
    updated = await memory.touch_scheduled_job_next_run(job_id, time.time())
    await audit.log_event(
        agent_id=job["agent_id"],
        event_type="scheduled_job_queued",
        details={"job_id": job_id, "job_name": job["name"]},
    )
    agent_name = get_all_agents().get(job["agent_id"], {}).get("name", job["agent_id"])
    return {"job": _serialize_job(updated, agent_name)}


@router.get("/jobs/{job_id}/runs")
async def get_scheduled_job_runs(job_id: int, limit: int = Query(default=20, ge=1, le=100)) -> dict:
    await _get_job_or_404(job_id)
    runs = await memory.list_scheduled_job_runs(job_id=job_id, limit=limit)
    return {"runs": runs, "total": len(runs)}
