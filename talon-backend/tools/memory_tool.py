"""
Agent-accessible memory tool.

Allows agents to explicitly recall past memories and store new facts
during a conversation.
"""

import json
import logging

from core import memory as mem

logger = logging.getLogger(__name__)


async def memory_recall(query: str, agent_id: str) -> str:
    """
    Search the agent's episodic and entity memory for information
    relevant to `query`.

    Returns a formatted string summary.
    """
    logger.info("[%s] memory_recall: %r", agent_id, query)

    parts = [f"Memory recall for: {query!r}\n"]

    # ── Episodic memories ─────────────────────────────────────────────────────
    episodes = await mem.search_episodic(agent_id, query, limit=5)
    if episodes:
        parts.append("📚 Episodic memories:")
        for ep in episodes:
            ts = ep.get("timestamp", 0)
            from datetime import datetime
            dt_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            parts.append(f"  [{dt_str}] {ep['summary']}")
    else:
        parts.append("📚 No episodic memories found.")

    # ── Entity memories ───────────────────────────────────────────────────────
    entities = await mem.search_entities(agent_id, query, limit=5)
    if entities:
        parts.append("\n🏷️ Entity memories:")
        for ent in entities:
            facts_str = json.dumps(ent["facts"], ensure_ascii=False)
            parts.append(f"  {ent['entity_name']} ({ent['entity_type']}): {facts_str}")
    else:
        parts.append("\n🏷️ No entity memories found.")

    return "\n".join(parts)


async def memory_store(key: str, value: str, agent_id: str) -> str:
    """
    Store a fact under `key` in the agent's entity memory.

    Args:
        key:      The entity/fact name (e.g. "slack_oncall_rotation").
        value:    The fact value as a string.
        agent_id: The calling agent's ID.

    Returns:
        Confirmation string.
    """
    logger.info("[%s] memory_store: key=%r value=%r", agent_id, key, value[:100])

    await mem.upsert_entity(
        agent_id=agent_id,
        entity_name=key,
        entity_type="fact",
        facts={"value": value},
    )
    return f"✅ Stored memory: {key!r} = {value!r}"
