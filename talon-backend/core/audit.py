from __future__ import annotations

"""
Audit trail logger for Project Talon.

All significant agent actions, tool calls, and policy decisions are written here.
"""

import json
import logging
import time
from typing import Any, Optional

import aiosqlite

from core import memory

logger = logging.getLogger(__name__)


async def log_event(
    agent_id: str,
    event_type: str,
    details: Optional[dict[str, Any]] = None,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> None:
    """
    Write an audit event.

    event_type examples:
      message_received, agent_response, tool_called, tool_result,
      policy_blocked, agent_paused, agent_resumed, error
    """
    details_str = json.dumps(details or {}, ensure_ascii=False, default=str)
    try:
        async with aiosqlite.connect(memory._DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO audit_log
                  (timestamp, agent_id, event_type, user_id, conversation_id, details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    agent_id,
                    event_type,
                    user_id,
                    conversation_id,
                    details_str,
                ),
            )
            await db.commit()
    except Exception as exc:
        # Audit must not crash the main flow
        logger.error("Audit log write failed: %s", exc)


async def get_events(
    agent_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    async with aiosqlite.connect(memory._DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        clauses = []
        params: list[Any] = []
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params += [limit, offset]

        async with db.execute(
            f"""
            SELECT id, timestamp, agent_id, event_type, user_id, conversation_id, details
            FROM audit_log
            {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "agent_id": row["agent_id"],
            "event_type": row["event_type"],
            "user_id": row["user_id"],
            "conversation_id": row["conversation_id"],
            "details": json.loads(row["details"]),
        }
        for row in rows
    ]


async def count_events(agent_id: Optional[str] = None) -> int:
    async with aiosqlite.connect(memory._DB_PATH) as db:
        if agent_id:
            async with db.execute(
                "SELECT COUNT(*) FROM audit_log WHERE agent_id = ?", (agent_id,)
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute("SELECT COUNT(*) FROM audit_log") as cursor:
                row = await cursor.fetchone()
    return row[0] if row else 0
