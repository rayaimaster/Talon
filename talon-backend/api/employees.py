"""
Agent (Employee) management endpoints.

Allows the frontend to:
  - Query individual agent details
  - Send test messages directly to agents (bypassing Teams)
  - Pause / resume agents
  - View agent memory and conversation history
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.admin_auth import require_admin_token
from channels.router import get_agent, get_all_agents
from core import audit, memory
from core.react_loop import get_react_loop

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/employees",
    tags=["employees"],
    dependencies=[Depends(require_admin_token)],
)


# ── Request / response models ─────────────────────────────────────────────────

class MessageRequest(BaseModel):
    message: str
    user: str = "test-user"
    conversation_id: Optional[str] = None


class MessageResponse(BaseModel):
    agent_id: str
    agent_name: str
    response: str
    conversation_id: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_employees() -> dict:
    """List all registered agents."""
    agents = get_all_agents()
    result = []
    for agent_id, config in agents.items():
        status = await memory.get_agent_status(agent_id)
        llm = config.get("llm", {})
        result.append(
            {
                "id": agent_id,
                "name": config.get("name"),
                "role": config.get("role"),
                "emoji": config.get("emoji", "🤖"),
                "color": config.get("color", "#6B7280"),
                "status": status,
                "model": config.get("model"),
                "provider": llm.get("provider", "anthropic"),
                "tools": config.get("tools", []),
            }
        )
    return {"employees": result}


@router.get("/{agent_id}")
async def get_employee(agent_id: str) -> dict:
    """Get details for a specific agent."""
    config = get_agent(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")

    status = await memory.get_agent_status(agent_id)
    conv_count = await memory.count_conversations(agent_id)
    msg_count = await memory.count_messages(agent_id)
    episodic_count = await memory.count_episodic(agent_id)
    entity_count = await memory.count_entities(agent_id)
    llm = config.get("llm", {})

    return {
        "id": agent_id,
        "name": config.get("name"),
        "role": config.get("role"),
        "emoji": config.get("emoji", "🤖"),
        "color": config.get("color", "#6B7280"),
        "status": status,
        "model": config.get("model"),
        "provider": llm.get("provider", "anthropic"),
        "tools": config.get("tools", []),
        "channels": config.get("channels", []),
        "system_prompt": config.get("system_prompt", ""),
        "stats": {
            "conversations": conv_count,
            "messages": msg_count,
            "episodic_memories": episodic_count,
            "entity_records": entity_count,
        },
    }


@router.post("/{agent_id}/message", response_model=MessageResponse)
async def send_message(agent_id: str, req: MessageRequest) -> MessageResponse:
    """
    Send a test message directly to an agent, bypassing Teams.

    This is the primary way to test agent behaviour locally.
    """
    config = get_agent(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")

    kill_switch = await memory.get_kill_switch_state()
    if kill_switch["active"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "The global kill switch is active. "
                f"{kill_switch.get('reason') or 'New work is currently halted.'}"
            ),
        )

    # Check agent is not paused
    status = await memory.get_agent_status(agent_id)
    if status == "paused":
        raise HTTPException(
            status_code=409, detail=f"Agent {agent_id!r} is paused. Resume it first."
        )

    # Use provided conversation_id or generate a new one
    conversation_id = req.conversation_id or f"direct-{uuid.uuid4().hex[:12]}"

    logger.info(
        "[%s] Direct message from %s: %r", agent_id, req.user, req.message[:100]
    )

    react = get_react_loop()
    try:
        response = await react.run(
            agent_config=config,
            message=req.message,
            conversation_id=conversation_id,
            user_id=req.user,
        )
    except RuntimeError as exc:
        # e.g. API key not set
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("[%s] ReAct loop error: %s", agent_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}")

    return MessageResponse(
        agent_id=agent_id,
        agent_name=config.get("name", agent_id),
        response=response,
        conversation_id=conversation_id,
    )


@router.post("/{agent_id}/pause")
async def pause_agent(agent_id: str) -> dict:
    """Pause an agent (it will not process new messages)."""
    config = get_agent(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")

    await memory.set_agent_status(agent_id, "paused")
    await audit.log_event(
        agent_id=agent_id,
        event_type="agent_paused",
        details={"previous_status": "active"},
    )
    logger.info("Agent %s paused", agent_id)
    return {"agent_id": agent_id, "status": "paused", "message": f"Agent {config.get('name')} paused."}


@router.post("/{agent_id}/resume")
async def resume_agent(agent_id: str) -> dict:
    """Resume a paused agent."""
    config = get_agent(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")

    await memory.set_agent_status(agent_id, "active")
    await audit.log_event(
        agent_id=agent_id,
        event_type="agent_resumed",
        details={"previous_status": "paused"},
    )
    logger.info("Agent %s resumed", agent_id)
    return {"agent_id": agent_id, "status": "active", "message": f"Agent {config.get('name')} resumed."}


@router.get("/{agent_id}/memory")
async def get_agent_memory(agent_id: str, limit: int = 20) -> dict:
    """Return the agent's episodic and entity memories."""
    config = get_agent(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")

    episodic = await memory.get_recent_episodic(agent_id, limit=limit)
    entities = await memory.search_entities(agent_id, "", limit=50)  # all entities

    return {
        "agent_id": agent_id,
        "episodic_memories": episodic,
        "entity_memories": entities,
    }


@router.get("/{agent_id}/history")
async def get_agent_history(agent_id: str, limit: int = 50) -> dict:
    """Return recent conversation history for an agent."""
    config = get_agent(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")

    messages = await memory.get_recent_conversations(agent_id=agent_id, limit=limit)
    return {
        "agent_id": agent_id,
        "messages": messages,
        "total": len(messages),
    }
