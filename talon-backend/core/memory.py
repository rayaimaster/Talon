"""
SQLite-backed memory service for Project Talon agents.

Tables:
  - conversations   : full message history per conversation
  - episodic_memory : summarized memories per agent
  - entity_memory   : structured facts about known entities
"""

import json
import logging
import time
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)

# Default DB path — overridden by settings at startup
_DB_PATH = "talon.db"


def set_db_path(path: str) -> None:
    global _DB_PATH
    # Strip the "sqlite:///" prefix if present
    _DB_PATH = path.replace("sqlite:///", "").replace("sqlite://", "")


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                agent_id    TEXT NOT NULL,
                role        TEXT NOT NULL,   -- 'user' | 'assistant' | 'tool'
                content     TEXT NOT NULL,   -- JSON-encoded for multi-part content
                timestamp   REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_id
            ON conversations (conversation_id, timestamp)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT NOT NULL,
                summary     TEXT NOT NULL,
                tags        TEXT NOT NULL DEFAULT '[]',  -- JSON array
                timestamp   REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_ep_agent
            ON episodic_memory (agent_id, timestamp)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS entity_memory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT 'fact',
                facts       TEXT NOT NULL DEFAULT '{}',  -- JSON object
                updated_at  REAL NOT NULL,
                UNIQUE(agent_id, entity_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   REAL NOT NULL,
                agent_id    TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                user_id     TEXT,
                conversation_id TEXT,
                details     TEXT NOT NULL DEFAULT '{}'   -- JSON
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_ts
            ON audit_log (timestamp DESC)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS agent_status (
                agent_id    TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'active',  -- active | paused
                updated_at  REAL NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS hitl_requests (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id        TEXT NOT NULL,
                task            TEXT NOT NULL,
                reason          TEXT NOT NULL,
                risk_level      TEXT NOT NULL DEFAULT 'medium',
                status          TEXT NOT NULL DEFAULT 'pending',
                requested_by    TEXT,
                details         TEXT NOT NULL DEFAULT '{}',
                resolution_note TEXT,
                created_at      REAL NOT NULL,
                updated_at      REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_hitl_status_created
            ON hitl_requests (status, created_at DESC)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS policy_rules (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                scope       TEXT NOT NULL,
                pattern     TEXT NOT NULL,
                action      TEXT NOT NULL DEFAULT 'block',
                description TEXT NOT NULL DEFAULT '',
                enabled     INTEGER NOT NULL DEFAULT 1,
                priority    INTEGER NOT NULL DEFAULT 100,
                updated_at  REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_policy_scope_priority
            ON policy_rules (scope, priority, id)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id            TEXT NOT NULL,
                name                TEXT NOT NULL,
                prompt              TEXT NOT NULL,
                interval_minutes    INTEGER NOT NULL,
                status              TEXT NOT NULL DEFAULT 'active',
                last_run_at         REAL,
                next_run_at         REAL NOT NULL,
                last_result         TEXT,
                last_error          TEXT,
                last_conversation_id TEXT,
                created_at          REAL NOT NULL,
                updated_at          REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_due
            ON scheduled_jobs (status, next_run_at)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_job_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id          INTEGER NOT NULL,
                status          TEXT NOT NULL,
                started_at      REAL NOT NULL,
                finished_at     REAL,
                conversation_id TEXT,
                response_preview TEXT,
                error           TEXT
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_scheduled_job_runs_job
            ON scheduled_job_runs (job_id, started_at DESC)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS agent_checkpoints (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT NOT NULL,
                label       TEXT NOT NULL,
                summary     TEXT NOT NULL DEFAULT '',
                created_by  TEXT,
                snapshot    TEXT NOT NULL,
                created_at  REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_checkpoints_agent_created
            ON agent_checkpoints (agent_id, created_at DESC)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  REAL NOT NULL
            )
        """)

        await db.commit()
    logger.info("Database initialised at %s", _DB_PATH)


# ─── Conversation history ─────────────────────────────────────────────────────

async def get_conversation_history(
    conversation_id: str,
    agent_id: str,
    limit: int = 50,
) -> list[dict]:
    """
    Return the last `limit` messages for a conversation as a list of
    Anthropic-compatible message dicts: [{"role": ..., "content": ...}, ...].
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT role, content
            FROM (
                SELECT id, role, content, timestamp
                FROM conversations
                WHERE conversation_id = ? AND agent_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            )
            ORDER BY timestamp ASC, id ASC
            """,
            (conversation_id, agent_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()

    messages = []
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        messages.append({"role": row["role"], "content": content})
    return messages


async def append_message(
    conversation_id: str,
    agent_id: str,
    role: str,
    content: Any,
) -> None:
    """Persist a single message to the conversation history."""
    if not isinstance(content, str):
        content_str = json.dumps(content, ensure_ascii=False)
    else:
        content_str = content

    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO conversations (conversation_id, agent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, agent_id, role, content_str, time.time()),
        )
        await db.commit()


# ─── Episodic memory ──────────────────────────────────────────────────────────

async def store_episodic(agent_id: str, summary: str, tags: list[str] | None = None) -> None:
    tags = tags or []
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO episodic_memory (agent_id, summary, tags, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (agent_id, summary, json.dumps(tags), time.time()),
        )
        await db.commit()


async def search_episodic(agent_id: str, query: str, limit: int = 5) -> list[dict]:
    """Simple keyword search over episodic memories."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # SQLite FTS not guaranteed; use LIKE for portability
        async with db.execute(
            """
            SELECT summary, tags, timestamp FROM episodic_memory
            WHERE agent_id = ?
              AND (summary LIKE ? OR tags LIKE ?)
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (agent_id, f"%{query}%", f"%{query}%", limit),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "summary": row["summary"],
            "tags": json.loads(row["tags"]),
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]


async def get_recent_episodic(agent_id: str, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT summary, tags, timestamp FROM episodic_memory
            WHERE agent_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (agent_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "summary": row["summary"],
            "tags": json.loads(row["tags"]),
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]


# ─── Entity memory ────────────────────────────────────────────────────────────

async def get_entity(agent_id: str, entity_name: str) -> Optional[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT entity_name, entity_type, facts, updated_at
            FROM entity_memory
            WHERE agent_id = ? AND entity_name = ?
            """,
            (agent_id, entity_name),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "entity_name": row["entity_name"],
        "entity_type": row["entity_type"],
        "facts": json.loads(row["facts"]),
        "updated_at": row["updated_at"],
    }


async def upsert_entity(
    agent_id: str,
    entity_name: str,
    entity_type: str,
    facts: dict,
) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        # Merge with existing facts
        existing = await get_entity(agent_id, entity_name)
        merged_facts = {}
        if existing:
            merged_facts.update(existing["facts"])
        merged_facts.update(facts)

        await db.execute(
            """
            INSERT INTO entity_memory (agent_id, entity_name, entity_type, facts, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, entity_name) DO UPDATE SET
                entity_type = excluded.entity_type,
                facts       = excluded.facts,
                updated_at  = excluded.updated_at
            """,
            (agent_id, entity_name, entity_type, json.dumps(merged_facts), time.time()),
        )
        await db.commit()


async def search_entities(agent_id: str, query: str, limit: int = 5) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT entity_name, entity_type, facts, updated_at
            FROM entity_memory
            WHERE agent_id = ?
              AND (entity_name LIKE ? OR facts LIKE ?)
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (agent_id, f"%{query}%", f"%{query}%", limit),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "entity_name": row["entity_name"],
            "entity_type": row["entity_type"],
            "facts": json.loads(row["facts"]),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


# ─── Agent status ─────────────────────────────────────────────────────────────

async def get_agent_status(agent_id: str) -> str:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status FROM agent_status WHERE agent_id = ?",
            (agent_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return row["status"] if row else "active"


async def set_agent_status(agent_id: str, status: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO agent_status (agent_id, status, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                status     = excluded.status,
                updated_at = excluded.updated_at
            """,
            (agent_id, status, time.time()),
        )
        await db.commit()


async def count_episodic(agent_id: Optional[str] = None) -> int:
    async with aiosqlite.connect(_DB_PATH) as db:
        if agent_id:
            async with db.execute(
                "SELECT COUNT(*) FROM episodic_memory WHERE agent_id = ?",
                (agent_id,),
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute("SELECT COUNT(*) FROM episodic_memory") as cursor:
                row = await cursor.fetchone()
    return row[0] if row else 0


async def count_entities(agent_id: Optional[str] = None) -> int:
    async with aiosqlite.connect(_DB_PATH) as db:
        if agent_id:
            async with db.execute(
                "SELECT COUNT(*) FROM entity_memory WHERE agent_id = ?",
                (agent_id,),
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute("SELECT COUNT(*) FROM entity_memory") as cursor:
                row = await cursor.fetchone()
    return row[0] if row else 0


async def create_hitl_request(
    agent_id: str,
    task: str,
    reason: str,
    risk_level: str = "medium",
    requested_by: Optional[str] = None,
    details: dict[str, Any] | None = None,
) -> dict:
    created_at = time.time()
    details_str = json.dumps(details or {}, ensure_ascii=False, default=str)

    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO hitl_requests (
                agent_id, task, reason, risk_level, status,
                requested_by, details, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                agent_id,
                task,
                reason,
                risk_level,
                requested_by,
                details_str,
                created_at,
                created_at,
            ),
        )
        await db.commit()
        request_id = cursor.lastrowid

    request = await get_hitl_request(request_id)
    if request is None:
        raise RuntimeError("Failed to create HITL request")
    return request


async def get_hitl_request(request_id: int) -> Optional[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, agent_id, task, reason, risk_level, status,
                   requested_by, details, resolution_note, created_at, updated_at
            FROM hitl_requests
            WHERE id = ?
            """,
            (request_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "task": row["task"],
        "reason": row["reason"],
        "risk_level": row["risk_level"],
        "status": row["status"],
        "requested_by": row["requested_by"],
        "details": json.loads(row["details"]),
        "resolution_note": row["resolution_note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def list_hitl_requests(
    status: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            async with db.execute(
                """
                SELECT id, agent_id, task, reason, risk_level, status,
                       requested_by, details, resolution_note, created_at, updated_at
                FROM hitl_requests
                WHERE status = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (status, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """
                SELECT id, agent_id, task, reason, risk_level, status,
                       requested_by, details, resolution_note, created_at, updated_at
                FROM hitl_requests
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "agent_id": row["agent_id"],
            "task": row["task"],
            "reason": row["reason"],
            "risk_level": row["risk_level"],
            "status": row["status"],
            "requested_by": row["requested_by"],
            "details": json.loads(row["details"]),
            "resolution_note": row["resolution_note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


async def count_hitl_requests(status: Optional[str] = None) -> int:
    async with aiosqlite.connect(_DB_PATH) as db:
        if status:
            async with db.execute(
                "SELECT COUNT(*) FROM hitl_requests WHERE status = ?",
                (status,),
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute("SELECT COUNT(*) FROM hitl_requests") as cursor:
                row = await cursor.fetchone()
    return row[0] if row else 0


async def update_hitl_request_status(
    request_id: int,
    status: str,
    resolution_note: Optional[str] = None,
    expected_current_status: Optional[str] = None,
) -> Optional[dict]:
    updated_at = time.time()
    async with aiosqlite.connect(_DB_PATH) as db:
        if expected_current_status is None:
            await db.execute(
                """
                UPDATE hitl_requests
                SET status = ?, resolution_note = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, resolution_note, updated_at, request_id),
            )
        else:
            await db.execute(
                """
                UPDATE hitl_requests
                SET status = ?, resolution_note = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (status, resolution_note, updated_at, request_id, expected_current_status),
            )
        await db.commit()

    return await get_hitl_request(request_id)


async def list_policy_rules(scope: Optional[str] = None) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if scope:
            async with db.execute(
                """
                SELECT id, name, scope, pattern, action, description, enabled, priority, updated_at
                FROM policy_rules
                WHERE scope = ?
                ORDER BY priority ASC, id ASC
                """,
                (scope,),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """
                SELECT id, name, scope, pattern, action, description, enabled, priority, updated_at
                FROM policy_rules
                ORDER BY priority ASC, id ASC
                """
            ) as cursor:
                rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "scope": row["scope"],
            "pattern": row["pattern"],
            "action": row["action"],
            "description": row["description"],
            "enabled": bool(row["enabled"]),
            "priority": row["priority"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


async def upsert_policy_rule(
    rule_id: str,
    name: str,
    scope: str,
    pattern: str,
    action: str = "block",
    description: str = "",
    enabled: bool = True,
    priority: int = 100,
) -> dict:
    updated_at = time.time()
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO policy_rules (id, name, scope, pattern, action, description, enabled, priority, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                scope = excluded.scope,
                pattern = excluded.pattern,
                action = excluded.action,
                description = excluded.description,
                enabled = excluded.enabled,
                priority = excluded.priority,
                updated_at = excluded.updated_at
            """,
            (
                rule_id,
                name,
                scope,
                pattern,
                action,
                description,
                1 if enabled else 0,
                priority,
                updated_at,
            ),
        )
        await db.commit()

    rules = await list_policy_rules()
    for rule in rules:
        if rule["id"] == rule_id:
            return rule
    raise RuntimeError(f"Failed to upsert policy rule {rule_id}")


async def get_policy_rule(rule_id: str) -> Optional[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, name, scope, pattern, action, description, enabled, priority, updated_at
            FROM policy_rules
            WHERE id = ?
            """,
            (rule_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "name": row["name"],
        "scope": row["scope"],
        "pattern": row["pattern"],
        "action": row["action"],
        "description": row["description"],
        "enabled": bool(row["enabled"]),
        "priority": row["priority"],
        "updated_at": row["updated_at"],
    }


async def create_scheduled_job(
    agent_id: str,
    name: str,
    prompt: str,
    interval_minutes: int,
    start_immediately: bool = False,
) -> dict:
    now = time.time()
    next_run_at = now if start_immediately else now + (interval_minutes * 60)
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO scheduled_jobs (
                agent_id, name, prompt, interval_minutes, status,
                next_run_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (agent_id, name, prompt, interval_minutes, next_run_at, now, now),
        )
        await db.commit()
        job_id = cursor.lastrowid

    job = await get_scheduled_job(job_id)
    if job is None:
        raise RuntimeError("Failed to create scheduled job")
    return job


async def get_scheduled_job(job_id: int) -> Optional[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, agent_id, name, prompt, interval_minutes, status,
                   last_run_at, next_run_at, last_result, last_error,
                   last_conversation_id, created_at, updated_at
            FROM scheduled_jobs
            WHERE id = ?
            """,
            (job_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "name": row["name"],
        "prompt": row["prompt"],
        "interval_minutes": row["interval_minutes"],
        "status": row["status"],
        "last_run_at": row["last_run_at"],
        "next_run_at": row["next_run_at"],
        "last_result": row["last_result"],
        "last_error": row["last_error"],
        "last_conversation_id": row["last_conversation_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def list_scheduled_jobs(agent_id: Optional[str] = None) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if agent_id:
            async with db.execute(
                """
                SELECT id, agent_id, name, prompt, interval_minutes, status,
                       last_run_at, next_run_at, last_result, last_error,
                       last_conversation_id, created_at, updated_at
                FROM scheduled_jobs
                WHERE agent_id = ?
                ORDER BY next_run_at ASC, id ASC
                """,
                (agent_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """
                SELECT id, agent_id, name, prompt, interval_minutes, status,
                       last_run_at, next_run_at, last_result, last_error,
                       last_conversation_id, created_at, updated_at
                FROM scheduled_jobs
                ORDER BY next_run_at ASC, id ASC
                """
            ) as cursor:
                rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "agent_id": row["agent_id"],
            "name": row["name"],
            "prompt": row["prompt"],
            "interval_minutes": row["interval_minutes"],
            "status": row["status"],
            "last_run_at": row["last_run_at"],
            "next_run_at": row["next_run_at"],
            "last_result": row["last_result"],
            "last_error": row["last_error"],
            "last_conversation_id": row["last_conversation_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


async def count_scheduled_jobs(status: Optional[str] = None) -> int:
    async with aiosqlite.connect(_DB_PATH) as db:
        if status:
            async with db.execute(
                "SELECT COUNT(*) FROM scheduled_jobs WHERE status = ?",
                (status,),
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute("SELECT COUNT(*) FROM scheduled_jobs") as cursor:
                row = await cursor.fetchone()
    return row[0] if row else 0


async def set_scheduled_job_status(job_id: int, status: str) -> Optional[dict]:
    now = time.time()
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            UPDATE scheduled_jobs
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, now, job_id),
        )
        await db.commit()
    return await get_scheduled_job(job_id)


async def touch_scheduled_job_next_run(job_id: int, next_run_at: float) -> Optional[dict]:
    now = time.time()
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            UPDATE scheduled_jobs
            SET next_run_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_run_at, now, job_id),
        )
        await db.commit()
    return await get_scheduled_job(job_id)


async def claim_due_scheduled_jobs(now: Optional[float] = None, limit: int = 10) -> list[dict]:
    now = now or time.time()
    due_jobs = await list_scheduled_jobs()
    claimed: list[dict] = []

    for job in due_jobs:
        if len(claimed) >= limit:
            break
        if job["status"] != "active":
            continue
        if job["next_run_at"] is None or job["next_run_at"] > now:
            continue

        async with aiosqlite.connect(_DB_PATH) as db:
            cursor = await db.execute(
                """
                UPDATE scheduled_jobs
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'active' AND next_run_at <= ?
                """,
                (now, job["id"], now),
            )
            await db.commit()
            rowcount = cursor.rowcount

        if rowcount:
            updated = await get_scheduled_job(job["id"])
            if updated is not None:
                claimed.append(updated)

    return claimed


async def finish_scheduled_job_run(
    job_id: int,
    status: str,
    next_run_at: float,
    response_preview: Optional[str] = None,
    error: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Optional[dict]:
    now = time.time()
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            UPDATE scheduled_jobs
            SET status = 'active',
                last_run_at = ?,
                next_run_at = ?,
                last_result = ?,
                last_error = ?,
                last_conversation_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now, next_run_at, response_preview, error, conversation_id, now, job_id),
        )
        await db.commit()
    return await get_scheduled_job(job_id)


async def create_scheduled_job_run(
    job_id: int,
    status: str,
    started_at: float,
    finished_at: Optional[float] = None,
    conversation_id: Optional[str] = None,
    response_preview: Optional[str] = None,
    error: Optional[str] = None,
) -> dict:
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO scheduled_job_runs (
                job_id, status, started_at, finished_at, conversation_id, response_preview, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, status, started_at, finished_at, conversation_id, response_preview, error),
        )
        await db.commit()
        run_id = cursor.lastrowid

    return {
        "id": run_id,
        "job_id": job_id,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "conversation_id": conversation_id,
        "response_preview": response_preview,
        "error": error,
    }


async def list_scheduled_job_runs(job_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, job_id, status, started_at, finished_at, conversation_id, response_preview, error
            FROM scheduled_job_runs
            WHERE job_id = ?
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            (job_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "job_id": row["job_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "conversation_id": row["conversation_id"],
            "response_preview": row["response_preview"],
            "error": row["error"],
        }
        for row in rows
    ]


async def _build_agent_snapshot(agent_id: str) -> dict:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """
            SELECT id, conversation_id, agent_id, role, content, timestamp
            FROM conversations
            WHERE agent_id = ?
            ORDER BY timestamp ASC, id ASC
            """,
            (agent_id,),
        ) as cursor:
            conversation_rows = await cursor.fetchall()

        async with db.execute(
            """
            SELECT id, agent_id, summary, tags, timestamp
            FROM episodic_memory
            WHERE agent_id = ?
            ORDER BY timestamp ASC, id ASC
            """,
            (agent_id,),
        ) as cursor:
            episodic_rows = await cursor.fetchall()

        async with db.execute(
            """
            SELECT id, agent_id, entity_name, entity_type, facts, updated_at
            FROM entity_memory
            WHERE agent_id = ?
            ORDER BY updated_at ASC, id ASC
            """,
            (agent_id,),
        ) as cursor:
            entity_rows = await cursor.fetchall()

        async with db.execute(
            """
            SELECT id, agent_id, task, reason, risk_level, status,
                   requested_by, details, resolution_note, created_at, updated_at
            FROM hitl_requests
            WHERE agent_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (agent_id,),
        ) as cursor:
            hitl_rows = await cursor.fetchall()

        async with db.execute(
            """
            SELECT id, agent_id, name, prompt, interval_minutes, status,
                   last_run_at, next_run_at, last_result, last_error,
                   last_conversation_id, created_at, updated_at
            FROM scheduled_jobs
            WHERE agent_id = ?
            ORDER BY id ASC
            """,
            (agent_id,),
        ) as cursor:
            scheduled_job_rows = await cursor.fetchall()

        scheduled_job_ids = [row["id"] for row in scheduled_job_rows]
        scheduled_run_rows = []
        if scheduled_job_ids:
            placeholders = ",".join("?" for _ in scheduled_job_ids)
            async with db.execute(
                f"""
                SELECT id, job_id, status, started_at, finished_at, conversation_id, response_preview, error
                FROM scheduled_job_runs
                WHERE job_id IN ({placeholders})
                ORDER BY started_at ASC, id ASC
                """,
                scheduled_job_ids,
            ) as cursor:
                scheduled_run_rows = await cursor.fetchall()

        async with db.execute(
            """
            SELECT agent_id, status, updated_at
            FROM agent_status
            WHERE agent_id = ?
            """,
            (agent_id,),
        ) as cursor:
            agent_status_row = await cursor.fetchone()

    return {
        "agent_id": agent_id,
        "agent_status": dict(agent_status_row) if agent_status_row else None,
        "conversations": [dict(row) for row in conversation_rows],
        "episodic_memory": [dict(row) for row in episodic_rows],
        "entity_memory": [dict(row) for row in entity_rows],
        "hitl_requests": [dict(row) for row in hitl_rows],
        "scheduled_jobs": [dict(row) for row in scheduled_job_rows],
        "scheduled_job_runs": [dict(row) for row in scheduled_run_rows],
    }


async def create_agent_checkpoint(
    agent_id: str,
    label: str,
    summary: str = "",
    created_by: Optional[str] = None,
) -> dict:
    snapshot = await _build_agent_snapshot(agent_id)
    created_at = time.time()
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO agent_checkpoints (agent_id, label, summary, created_by, snapshot, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                label,
                summary,
                created_by,
                json.dumps(snapshot, ensure_ascii=False, default=str),
                created_at,
            ),
        )
        await db.commit()
        checkpoint_id = cursor.lastrowid

    checkpoint = await get_agent_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise RuntimeError("Failed to create checkpoint")
    return checkpoint


async def get_agent_checkpoint(checkpoint_id: int) -> Optional[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, agent_id, label, summary, created_by, snapshot, created_at
            FROM agent_checkpoints
            WHERE id = ?
            """,
            (checkpoint_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "label": row["label"],
        "summary": row["summary"],
        "created_by": row["created_by"],
        "snapshot": json.loads(row["snapshot"]),
        "created_at": row["created_at"],
    }


async def list_agent_checkpoints(agent_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if agent_id:
            async with db.execute(
                """
                SELECT id, agent_id, label, summary, created_by, snapshot, created_at
                FROM agent_checkpoints
                WHERE agent_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (agent_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """
                SELECT id, agent_id, label, summary, created_by, snapshot, created_at
                FROM agent_checkpoints
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "agent_id": row["agent_id"],
            "label": row["label"],
            "summary": row["summary"],
            "created_by": row["created_by"],
            "snapshot": json.loads(row["snapshot"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


async def restore_agent_checkpoint(
    checkpoint_id: int,
    create_safety_checkpoint: bool = True,
    created_by: Optional[str] = None,
) -> dict:
    checkpoint = await get_agent_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise ValueError(f"Checkpoint {checkpoint_id} not found")

    snapshot = checkpoint["snapshot"]
    agent_id = checkpoint["agent_id"]

    current_jobs = await list_scheduled_jobs(agent_id=agent_id)
    if any(job["status"] == "running" for job in current_jobs):
        raise RuntimeError(
            f"Cannot restore checkpoint for {agent_id!r} while a scheduled job is running."
        )

    safety_checkpoint = None
    if create_safety_checkpoint:
        safety_checkpoint = await create_agent_checkpoint(
            agent_id=agent_id,
            label=f"Auto backup before restore {checkpoint_id}",
            summary=f"Automatic safeguard created before restoring checkpoint {checkpoint_id}",
            created_by=created_by,
        )

    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("BEGIN")
        try:
            async with db.execute(
                "SELECT id FROM scheduled_jobs WHERE agent_id = ?",
                (agent_id,),
            ) as cursor:
                current_job_rows = await cursor.fetchall()
            current_job_ids = [row[0] for row in current_job_rows]

            if current_job_ids:
                placeholders = ",".join("?" for _ in current_job_ids)
                await db.execute(
                    f"DELETE FROM scheduled_job_runs WHERE job_id IN ({placeholders})",
                    current_job_ids,
                )

            await db.execute("DELETE FROM conversations WHERE agent_id = ?", (agent_id,))
            await db.execute("DELETE FROM episodic_memory WHERE agent_id = ?", (agent_id,))
            await db.execute("DELETE FROM entity_memory WHERE agent_id = ?", (agent_id,))
            await db.execute("DELETE FROM hitl_requests WHERE agent_id = ?", (agent_id,))
            await db.execute("DELETE FROM scheduled_jobs WHERE agent_id = ?", (agent_id,))
            await db.execute("DELETE FROM agent_status WHERE agent_id = ?", (agent_id,))

            for row in snapshot.get("conversations", []):
                await db.execute(
                    """
                    INSERT INTO conversations (id, conversation_id, agent_id, role, content, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["conversation_id"],
                        row["agent_id"],
                        row["role"],
                        row["content"],
                        row["timestamp"],
                    ),
                )

            for row in snapshot.get("episodic_memory", []):
                await db.execute(
                    """
                    INSERT INTO episodic_memory (id, agent_id, summary, tags, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (row["id"], row["agent_id"], row["summary"], row["tags"], row["timestamp"]),
                )

            for row in snapshot.get("entity_memory", []):
                await db.execute(
                    """
                    INSERT INTO entity_memory (id, agent_id, entity_name, entity_type, facts, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["agent_id"],
                        row["entity_name"],
                        row["entity_type"],
                        row["facts"],
                        row["updated_at"],
                    ),
                )

            for row in snapshot.get("hitl_requests", []):
                await db.execute(
                    """
                    INSERT INTO hitl_requests (
                        id, agent_id, task, reason, risk_level, status,
                        requested_by, details, resolution_note, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["agent_id"],
                        row["task"],
                        row["reason"],
                        row["risk_level"],
                        row["status"],
                        row["requested_by"],
                        row["details"],
                        row["resolution_note"],
                        row["created_at"],
                        row["updated_at"],
                    ),
                )

            for row in snapshot.get("scheduled_jobs", []):
                await db.execute(
                    """
                    INSERT INTO scheduled_jobs (
                        id, agent_id, name, prompt, interval_minutes, status,
                        last_run_at, next_run_at, last_result, last_error,
                        last_conversation_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["agent_id"],
                        row["name"],
                        row["prompt"],
                        row["interval_minutes"],
                        row["status"],
                        row["last_run_at"],
                        row["next_run_at"],
                        row["last_result"],
                        row["last_error"],
                        row["last_conversation_id"],
                        row["created_at"],
                        row["updated_at"],
                    ),
                )

            for row in snapshot.get("scheduled_job_runs", []):
                await db.execute(
                    """
                    INSERT INTO scheduled_job_runs (
                        id, job_id, status, started_at, finished_at, conversation_id, response_preview, error
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["job_id"],
                        row["status"],
                        row["started_at"],
                        row["finished_at"],
                        row["conversation_id"],
                        row["response_preview"],
                        row["error"],
                    ),
                )

            agent_status = snapshot.get("agent_status")
            if agent_status:
                await db.execute(
                    """
                    INSERT INTO agent_status (agent_id, status, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        agent_status["agent_id"],
                        agent_status["status"],
                        agent_status["updated_at"],
                    ),
                )

            await db.commit()
        except Exception:
            await db.rollback()
            raise

    restored_checkpoint = await get_agent_checkpoint(checkpoint_id)
    return {
        "checkpoint": restored_checkpoint,
        "safety_checkpoint": safety_checkpoint,
    }


async def get_system_state(key: str) -> Optional[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT key, value, updated_at
            FROM system_state
            WHERE key = ?
            """,
            (key,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "key": row["key"],
        "value": json.loads(row["value"]),
        "updated_at": row["updated_at"],
    }


async def set_system_state(key: str, value: Any) -> dict:
    updated_at = time.time()
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO system_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False, default=str), updated_at),
        )
        await db.commit()

    state = await get_system_state(key)
    if state is None:
        raise RuntimeError(f"Failed to set system state {key}")
    return state


async def get_kill_switch_state() -> dict:
    state = await get_system_state("kill_switch")
    if state is None:
        return {
            "active": False,
            "reason": "",
            "updated_by": None,
            "activated_at": None,
        }
    value = state["value"]
    return {
        "active": bool(value.get("active", False)),
        "reason": value.get("reason", ""),
        "updated_by": value.get("updated_by"),
        "activated_at": value.get("activated_at"),
    }


async def set_kill_switch_state(
    active: bool,
    reason: str = "",
    updated_by: Optional[str] = None,
) -> dict:
    current = await get_kill_switch_state()
    payload = {
        "active": active,
        "reason": reason,
        "updated_by": updated_by,
        "activated_at": time.time() if active else current.get("activated_at"),
    }
    if not active:
        payload["activated_at"] = None
    await set_system_state("kill_switch", payload)
    return await get_kill_switch_state()


# ─── Stats helpers ────────────────────────────────────────────────────────────

async def count_conversations(agent_id: Optional[str] = None) -> int:
    async with aiosqlite.connect(_DB_PATH) as db:
        if agent_id:
            async with db.execute(
                "SELECT COUNT(DISTINCT conversation_id) FROM conversations WHERE agent_id = ?",
                (agent_id,),
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute(
                "SELECT COUNT(DISTINCT conversation_id) FROM conversations"
            ) as cursor:
                row = await cursor.fetchone()
    return row[0] if row else 0


async def count_messages(agent_id: Optional[str] = None) -> int:
    async with aiosqlite.connect(_DB_PATH) as db:
        if agent_id:
            async with db.execute(
                "SELECT COUNT(*) FROM conversations WHERE agent_id = ?",
                (agent_id,),
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute("SELECT COUNT(*) FROM conversations") as cursor:
                row = await cursor.fetchone()
    return row[0] if row else 0


async def get_recent_conversations(agent_id: Optional[str] = None, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if agent_id:
            async with db.execute(
                """
                SELECT conversation_id, agent_id, role, content, timestamp
                FROM conversations
                WHERE agent_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (agent_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """
                SELECT conversation_id, agent_id, role, content, timestamp
                FROM conversations
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()

    return [
        {
            "conversation_id": row["conversation_id"],
            "agent_id": row["agent_id"],
            "role": row["role"],
            "content": row["content"],
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]
