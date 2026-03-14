"""
Dashboard REST API endpoints.

Provides platform-wide metrics and activity feed for the frontend.
"""

import time
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.admin_auth import require_admin_token
from channels.router import get_all_agents
from core import memory, audit

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_admin_token)],
)


@router.get("/metrics")
async def get_metrics() -> dict:
    """Platform-wide metrics for the dashboard overview."""
    agents = get_all_agents()
    agent_statuses = {}
    for agent_id in agents:
        agent_statuses[agent_id] = await memory.get_agent_status(agent_id)

    active_count = sum(1 for s in agent_statuses.values() if s == "active")
    total_conversations = await memory.count_conversations()
    total_messages = await memory.count_messages()
    total_events = await audit.count_events()
    total_episodic = await memory.count_episodic()
    total_entities = await memory.count_entities()
    pending_hitl = await memory.count_hitl_requests(status="pending")
    total_schedules = await memory.count_scheduled_jobs()
    active_schedules = await memory.count_scheduled_jobs(status="active")
    paused_schedules = await memory.count_scheduled_jobs(status="paused")

    return {
        "agents": {
            "total": len(agents),
            "active": active_count,
            "paused": len(agents) - active_count,
        },
        "conversations": {
            "total": total_conversations,
        },
        "messages": {
            "total": total_messages,
        },
        "audit_events": {
            "total": total_events,
        },
        "memory": {
            "episodic": total_episodic,
            "entities": total_entities,
        },
        "hitl": {
            "pending": pending_hitl,
        },
        "scheduled_jobs": {
            "active": active_schedules,
            "paused": paused_schedules,
            "total": total_schedules,
        },
        "platform": {
            "name": "Project Talon",
            "version": "1.0.0",
            "uptime_since": _start_time,
        },
    }


@router.get("/employees")
async def get_employees() -> dict:
    """Return all agents with their current status and config."""
    agents = get_all_agents()
    result = []
    for agent_id, config in agents.items():
        status = await memory.get_agent_status(agent_id)
        conv_count = await memory.count_conversations(agent_id)
        msg_count = await memory.count_messages(agent_id)
        episodic_count = await memory.count_episodic(agent_id)
        entity_count = await memory.count_entities(agent_id)
        audit_count = await audit.count_events(agent_id)
        llm = config.get("llm", {})
        result.append(
            {
                "id": agent_id,
                "name": config.get("name"),
                "role": config.get("role"),
                "emoji": config.get("emoji", "🤖"),
                "color": config.get("color", "#6B7280"),
                "status": status,
                "model": config.get("model", "claude-3-5-haiku-20241022"),
                "provider": llm.get("provider", "anthropic"),
                "tools": config.get("tools", []),
                "channels": config.get("channels", []),
                "stats": {
                    "conversations": conv_count,
                    "messages": msg_count,
                    "episodic_memories": episodic_count,
                    "entity_records": entity_count,
                    "audit_events": audit_count,
                },
            }
        )
    return {"employees": result}


@router.get("/activity")
async def get_activity(limit: int = Query(default=50, le=200)) -> dict:
    """Recent activity feed across all agents."""
    events = await audit.get_events(limit=limit)
    agents = get_all_agents()

    activities = []
    for ev in events:
        agent_config = agents.get(ev["agent_id"], {})
        activities.append(
            {
                "id": ev["id"],
                "timestamp": ev["timestamp"],
                "agent_id": ev["agent_id"],
                "agent_name": agent_config.get("name", ev["agent_id"]),
                "agent_emoji": agent_config.get("emoji", "🤖"),
                "event_type": ev["event_type"],
                "user_id": ev.get("user_id"),
                "conversation_id": ev.get("conversation_id"),
                "details": ev.get("details", {}),
            }
        )
    return {"activities": activities, "total": len(activities)}


# Track startup time for uptime reporting
_start_time = time.time()
