from __future__ import annotations

"""
Simple recurring job scheduler for Project Talon.
"""

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from typing import Optional

from channels.router import get_agent
from core import audit, memory
from core.react_loop import get_react_loop

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


class SchedulerService:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="talon-scheduler")
        logger.info("Scheduler service started")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        logger.info("Scheduler service stopped")

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                due_jobs = await memory.claim_due_scheduled_jobs(limit=5)
                for job in due_jobs:
                    await self._execute_job(job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Scheduler loop error: %s", exc, exc_info=True)

            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                continue

    async def _execute_job(self, job: dict) -> None:
        started_at = time.time()
        run_conversation_id = f"schedule-{job['id']}-{uuid.uuid4().hex[:10]}"
        next_run_at = started_at + (job["interval_minutes"] * 60)

        kill_switch = await memory.get_kill_switch_state()
        if kill_switch["active"]:
            response_preview = (
                "Skipped scheduled run because the global kill switch is active."
            )
            await memory.create_scheduled_job_run(
                job_id=job["id"],
                status="skipped",
                started_at=started_at,
                finished_at=time.time(),
                response_preview=response_preview,
            )
            await memory.finish_scheduled_job_run(
                job_id=job["id"],
                status="skipped",
                next_run_at=next_run_at,
                response_preview=response_preview,
            )
            await audit.log_event(
                agent_id=job["agent_id"],
                event_type="scheduled_job_skipped",
                details={"job_id": job["id"], "job_name": job["name"], "reason": "kill_switch"},
            )
            return

        agent_config = get_agent(job["agent_id"])
        if not agent_config:
            error = f"Agent {job['agent_id']!r} not found"
            await memory.create_scheduled_job_run(
                job_id=job["id"],
                status="failed",
                started_at=started_at,
                finished_at=time.time(),
                error=error,
            )
            await memory.finish_scheduled_job_run(
                job_id=job["id"],
                status="failed",
                next_run_at=next_run_at,
                error=error,
            )
            await audit.log_event(
                agent_id=job["agent_id"],
                event_type="scheduled_job_failed",
                details={"job_id": job["id"], "job_name": job["name"], "error": error},
            )
            return

        agent_status = await memory.get_agent_status(job["agent_id"])
        if agent_status == "paused":
            response_preview = "Skipped scheduled run because the agent is paused."
            await memory.create_scheduled_job_run(
                job_id=job["id"],
                status="skipped",
                started_at=started_at,
                finished_at=time.time(),
                response_preview=response_preview,
            )
            await memory.finish_scheduled_job_run(
                job_id=job["id"],
                status="skipped",
                next_run_at=next_run_at,
                response_preview=response_preview,
            )
            await audit.log_event(
                agent_id=job["agent_id"],
                event_type="scheduled_job_skipped",
                details={"job_id": job["id"], "job_name": job["name"], "reason": "agent_paused"},
            )
            return

        await audit.log_event(
            agent_id=job["agent_id"],
            event_type="scheduled_job_started",
            conversation_id=run_conversation_id,
            details={"job_id": job["id"], "job_name": job["name"], "prompt": job["prompt"][:300]},
        )

        try:
            response = await get_react_loop().run(
                agent_config=agent_config,
                message=job["prompt"],
                conversation_id=run_conversation_id,
                user_id="scheduler",
            )
            preview = response[:500]
            await memory.create_scheduled_job_run(
                job_id=job["id"],
                status="success",
                started_at=started_at,
                finished_at=time.time(),
                conversation_id=run_conversation_id,
                response_preview=preview,
            )
            await memory.finish_scheduled_job_run(
                job_id=job["id"],
                status="success",
                next_run_at=next_run_at,
                response_preview=preview,
                conversation_id=run_conversation_id,
            )
            await audit.log_event(
                agent_id=job["agent_id"],
                event_type="scheduled_job_completed",
                conversation_id=run_conversation_id,
                details={"job_id": job["id"], "job_name": job["name"], "response_preview": preview},
            )
        except Exception as exc:
            error = str(exc)
            logger.error("Scheduled job %s failed: %s", job["id"], exc, exc_info=True)
            await memory.create_scheduled_job_run(
                job_id=job["id"],
                status="failed",
                started_at=started_at,
                finished_at=time.time(),
                conversation_id=run_conversation_id,
                error=error,
            )
            await memory.finish_scheduled_job_run(
                job_id=job["id"],
                status="failed",
                next_run_at=next_run_at,
                error=error,
                conversation_id=run_conversation_id,
            )
            await audit.log_event(
                agent_id=job["agent_id"],
                event_type="scheduled_job_failed",
                conversation_id=run_conversation_id,
                details={"job_id": job["id"], "job_name": job["name"], "error": error},
            )


_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
