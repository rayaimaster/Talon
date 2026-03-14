"""
WebSocket channel for Project Talon.

Provides real-time bidirectional chat with digital employees via WebSocket.

Endpoint: ws://<host>/ws/chat/{agent_id}/{session_id}

Message Protocol (JSON):

  Client → Server:
    { "type": "message", "text": "Hello Alex!", "user": "john.doe" }
    { "type": "ping" }

  Server → Client:
    { "type": "typing",      "agent": "alex-sre" }
    { "type": "tool_call",   "tool": "web_search", "input": "kubernetes pod crash" }
    { "type": "tool_result", "tool": "web_search", "result": "..." }
    { "type": "message",     "text": "Here's what I found...", "agent": "Alex",
                             "agent_id": "alex-sre", "timestamp": 1234567890 }
    { "type": "error",       "text": "Something went wrong" }
    { "type": "pong" }
"""

import json
import logging
import time
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse

from channels.router import get_agent, get_all_agents
from core import memory, audit
from core.react_loop import get_react_loop

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Connection Manager ─────────────────────────────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections per agent+session."""

    def __init__(self) -> None:
        # agent_id → {session_id → WebSocket}
        self._connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        agent_id: str,
        session_id: str,
    ) -> None:
        await websocket.accept()
        if agent_id not in self._connections:
            self._connections[agent_id] = {}
        self._connections[agent_id][session_id] = websocket
        logger.info(
            "WS connected: agent=%s session=%s total=%d",
            agent_id, session_id, self._total_connections(),
        )

    def disconnect(self, agent_id: str, session_id: str) -> None:
        if agent_id in self._connections:
            self._connections[agent_id].pop(session_id, None)
            if not self._connections[agent_id]:
                del self._connections[agent_id]
        logger.info("WS disconnected: agent=%s session=%s", agent_id, session_id)

    async def send(
        self,
        agent_id: str,
        session_id: str,
        message: dict,
    ) -> None:
        """Send a JSON message to a specific session."""
        ws = self._connections.get(agent_id, {}).get(session_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning(
                    "WS send failed agent=%s session=%s: %s",
                    agent_id, session_id, exc,
                )

    def _total_connections(self) -> int:
        return sum(len(sessions) for sessions in self._connections.values())

    @property
    def active_connections(self) -> int:
        return self._total_connections()


manager = ConnectionManager()


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@router.websocket("/ws/chat/{agent_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    agent_id: str,
    session_id: str,
) -> None:
    """
    Real-time WebSocket chat with a digital employee.

    Path parameters:
        agent_id:   Agent identifier (e.g. "alex-sre")
        session_id: Client-generated session UUID for conversation continuity
    """
    # Validate agent exists
    agent_config = get_agent(agent_id)
    if not agent_config:
        await websocket.close(code=4004, reason=f"Agent {agent_id!r} not found")
        return

    await manager.connect(websocket, agent_id, session_id)

    # Send welcome message
    agent_name = agent_config.get("name", agent_id)
    agent_role = agent_config.get("role", "Digital Employee")
    await manager.send(
        agent_id, session_id,
        {
            "type": "welcome",
            "agent": agent_name,
            "agent_id": agent_id,
            "role": agent_role,
            "emoji": agent_config.get("emoji", "🤖"),
            "color": agent_config.get("color", "#6B7280"),
            "session_id": session_id,
            "timestamp": time.time(),
        },
    )

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send(
                    agent_id, session_id,
                    {"type": "error", "text": "Invalid JSON"},
                )
                continue

            msg_type = data.get("type", "message")

            if msg_type == "ping":
                await manager.send(agent_id, session_id, {"type": "pong"})
                continue

            if msg_type == "message":
                text = data.get("text", "").strip()
                if not text:
                    continue

                user = data.get("user", "web-user")
                await _run_agent(
                    agent_config=agent_config,
                    session_id=session_id,
                    text=text,
                    user=user,
                )

    except WebSocketDisconnect:
        manager.disconnect(agent_id, session_id)
    except Exception as exc:
        logger.error(
            "WS error agent=%s session=%s: %s", agent_id, session_id, exc,
            exc_info=True,
        )
        try:
            await manager.send(
                agent_id, session_id,
                {"type": "error", "text": f"Server error: {exc}"},
            )
        except Exception:
            pass
        manager.disconnect(agent_id, session_id)


async def _run_agent(
    agent_config: dict,
    session_id: str,
    text: str,
    user: str,
) -> None:
    """
    Run the ReAct loop for this agent and stream events back via WebSocket.
    """
    agent_id = agent_config["id"]

    # Use session_id as conversation_id for persistence
    conversation_id = f"ws-{session_id}"

    kill_switch = await memory.get_kill_switch_state()
    if kill_switch["active"]:
        await manager.send(
            agent_id, session_id,
            {
                "type": "error",
                "text": (
                    "⛔ The global kill switch is active. "
                    f"{kill_switch.get('reason') or 'New work is currently halted.'}"
                ),
            },
        )
        return

    # Check agent status
    status = await memory.get_agent_status(agent_id)
    if status == "paused":
        await manager.send(
            agent_id, session_id,
            {
                "type": "error",
                "text": (
                    f"⏸️ {agent_config.get('name', 'Agent')} is currently paused. "
                    "An admin needs to resume this agent."
                ),
            },
        )
        return

    # Build WS callback for streaming events
    async def ws_callback(event: dict) -> None:
        await manager.send(agent_id, session_id, event)

    react = get_react_loop()
    try:
        response_text = await react.run(
            agent_config=agent_config,
            message=text,
            conversation_id=conversation_id,
            user_id=user,
            ws_callback=ws_callback,
        )
    except RuntimeError as exc:
        await manager.send(
            agent_id, session_id,
            {"type": "error", "text": f"⚠️ Configuration error: {exc}"},
        )
        return
    except Exception as exc:
        logger.error(
            "[%s] WS ReAct loop error: %s", agent_id, exc, exc_info=True
        )
        await manager.send(
            agent_id, session_id,
            {"type": "error", "text": f"⚠️ Agent error: {exc}"},
        )
        return

    # Send final message to client
    await manager.send(
        agent_id, session_id,
        {
            "type": "message",
            "text": response_text,
            "agent": agent_config.get("name", agent_id),
            "agent_id": agent_id,
            "timestamp": time.time(),
        },
    )


# ── REST API endpoints for webchat ────────────────────────────────────────────

@router.get("/api/agents", tags=["agents"])
async def list_agents() -> dict:
    """
    List all configured digital employees.
    Used by the webchat frontend for the agent picker page.
    """
    agents = get_all_agents()
    result = []
    for agent_id, config in agents.items():
        status = await memory.get_agent_status(agent_id)
        llm_config = config.get("llm", {})
        result.append(
            {
                "id": agent_id,
                "name": config.get("name"),
                "role": config.get("role"),
                "emoji": config.get("emoji", "🤖"),
                "color": config.get("color", "#6B7280"),
                "status": status,
                "provider": llm_config.get("provider", "anthropic"),
                "model": llm_config.get("model") or config.get("model", "claude-3-5-haiku-20241022"),
                "tools": config.get("tools", []),
                "description": _agent_description(config),
            }
        )
    return {"agents": result}


@router.get("/api/agents/{agent_id}", tags=["agents"])
async def get_agent_info(agent_id: str) -> dict:
    """Get info for a specific agent."""
    config = get_agent(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")

    status = await memory.get_agent_status(agent_id)
    conv_count = await memory.count_conversations(agent_id)
    msg_count = await memory.count_messages(agent_id)
    llm_config = config.get("llm", {})

    return {
        "id": agent_id,
        "name": config.get("name"),
        "role": config.get("role"),
        "emoji": config.get("emoji", "🤖"),
        "color": config.get("color", "#6B7280"),
        "status": status,
        "provider": llm_config.get("provider", "anthropic"),
        "model": llm_config.get("model") or config.get("model", "claude-3-5-haiku-20241022"),
        "tools": config.get("tools", []),
        "channels": config.get("channels", []),
        "description": _agent_description(config),
        "stats": {
            "conversations": conv_count,
            "messages": msg_count,
        },
    }


@router.get("/api/chat/{agent_id}/history/{session_id}", tags=["agents"])
async def get_chat_history(agent_id: str, session_id: str) -> dict:
    """
    Load conversation history for a webchat session.
    The webchat uses session_id as the conversation_id prefix.
    """
    config = get_agent(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")

    conversation_id = f"ws-{session_id}"
    messages = await memory.get_conversation_history(
        conversation_id=conversation_id,
        agent_id=agent_id,
        limit=100,
    )

    # Flatten content blocks to plain text for the webchat
    result = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            text = content
            msg_type = "message"
        elif isinstance(content, list):
            # Check for tool results (skip — they're internal)
            block_types = {
                b.get("type") for b in content if isinstance(b, dict)
            }
            if "tool_result" in block_types:
                continue
            text_parts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            text = "\n".join(text_parts).strip()
            msg_type = "message"
            # Include tool_use as tool_call messages
            tool_blocks = [
                b for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            for tb in tool_blocks:
                result.append({
                    "type": "tool_call",
                    "role": "assistant",
                    "tool": tb.get("name", ""),
                    "input": json.dumps(tb.get("input", {})),
                })
        else:
            text = str(content)
            msg_type = "message"

        if text:
            result.append({
                "type": msg_type,
                "role": role,
                "text": text,
                "agent": config.get("name") if role == "assistant" else None,
                "agent_id": agent_id if role == "assistant" else None,
            })

    return {
        "agent_id": agent_id,
        "session_id": session_id,
        "messages": result,
        "total": len(result),
    }


@router.get("/api/ws/stats", tags=["system"])
async def ws_stats() -> dict:
    """Return WebSocket connection stats."""
    return {
        "active_connections": manager.active_connections,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _agent_description(config: dict) -> str:
    """Extract a short description from the system prompt."""
    prompt = config.get("system_prompt", "")
    if not prompt:
        return config.get("role", "Digital Employee")
    # Take first two sentences of the system prompt
    sentences = prompt.strip().split(".")
    desc = ". ".join(sentences[:2]).strip()
    if desc and not desc.endswith("."):
        desc += "."
    return desc[:200]
