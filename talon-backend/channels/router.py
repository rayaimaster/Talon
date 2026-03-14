"""
Message router — decides which agent should handle a given message.

Routing rules (in priority order):
  1. Explicit @mention of agent name  → route to that agent
  2. Channel name matches agent config → route to channel's agent
  3. Fallback                          → route to the first configured agent
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Populated at startup from agents.yaml
_agents: dict[str, dict] = {}


def load_agents(agents: dict[str, dict]) -> None:
    """Register all agents from the config. Called at app startup."""
    global _agents
    _agents = agents
    logger.info("Router loaded %d agents: %s", len(agents), list(agents.keys()))


def route_message(
    text: str,
    channel_name: Optional[str] = None,
    mentioned_agent: Optional[str] = None,
) -> Optional[dict]:
    """
    Determine which agent config should handle this message.

    Args:
        text:            The raw message text.
        channel_name:    The Teams channel name (e.g. "#incidents").
        mentioned_agent: Agent name extracted from an @mention (optional).

    Returns:
        The agent config dict, or None if no match.
    """
    if not _agents:
        logger.warning("No agents loaded — cannot route message")
        return None

    # ── 1. Explicit @mention ──────────────────────────────────────────────────
    if mentioned_agent:
        for agent_id, config in _agents.items():
            if config.get("name", "").lower() == mentioned_agent.lower():
                logger.info("Route by @mention: %s → %s", mentioned_agent, agent_id)
                return config
        # Try matching by agent_id
        if mentioned_agent in _agents:
            logger.info("Route by agent ID: %s", mentioned_agent)
            return _agents[mentioned_agent]

    # ── 2. Channel-based routing ──────────────────────────────────────────────
    if channel_name:
        channel_lower = channel_name.lower()
        for agent_id, config in _agents.items():
            for ch in config.get("channels", []):
                ch_clean = ch.replace("teams:", "").lower()
                if ch_clean == channel_lower or ch_clean == f"#{channel_lower}":
                    logger.info(
                        "Route by channel: %s → %s", channel_name, agent_id
                    )
                    return config

    # ── 3. Keyword heuristics ─────────────────────────────────────────────────
    text_lower = text.lower()
    # SRE keywords
    sre_keywords = {"incident", "alert", "kubernetes", "k8s", "pod", "deploy", "monitoring"}
    if any(kw in text_lower for kw in sre_keywords):
        if "alex-sre" in _agents:
            logger.info("Route by SRE keywords → alex-sre")
            return _agents["alex-sre"]

    # IT keywords
    it_keywords = {"password", "reset", "vpn", "printer", "install", "laptop"}
    if any(kw in text_lower for kw in it_keywords):
        if "dana-helpdesk" in _agents:
            logger.info("Route by IT keywords → dana-helpdesk")
            return _agents["dana-helpdesk"]

    # Data keywords
    data_keywords = {"data", "sql", "query", "analytics", "report", "dashboard"}
    if any(kw in text_lower for kw in data_keywords):
        if "morgan-data" in _agents:
            logger.info("Route by data keywords → morgan-data")
            return _agents["morgan-data"]

    # ── 4. Fallback to first agent ────────────────────────────────────────────
    first_agent = next(iter(_agents.values()))
    logger.info("Route fallback → %s", first_agent.get("id"))
    return first_agent


def extract_mention(text: str, bot_name: str = "") -> tuple[str, Optional[str]]:
    """
    Remove @mentions from a Teams message and extract the mentioned agent name.

    Returns:
        (clean_text, mentioned_agent_name_or_None)
    """
    mentioned = None
    clean = text

    # Teams @mentions look like: <at>AgentName</at>
    at_pattern = re.compile(r"<at>(.*?)</at>", re.IGNORECASE)
    mentions = at_pattern.findall(text)
    clean = at_pattern.sub("", clean).strip()

    for m in mentions:
        m_lower = m.lower()
        # Check if this mention matches a known agent name
        for agent_id, config in _agents.items():
            if config.get("name", "").lower() == m_lower:
                mentioned = config.get("name")
                break
        # If it's the bot itself, that's just the trigger — not an agent mention
        if bot_name and m_lower == bot_name.lower():
            mentioned = None

    # Also handle plain @Name mentions (Slack-style, for testing)
    plain_at = re.compile(r"@(\w+)")
    for m in plain_at.findall(text):
        for agent_id, config in _agents.items():
            if config.get("name", "").lower() == m.lower():
                mentioned = config.get("name")
                clean = clean.replace(f"@{m}", "").strip()
                break

    return clean, mentioned


def get_all_agents() -> dict[str, dict]:
    return _agents


def get_agent(agent_id: str) -> Optional[dict]:
    return _agents.get(agent_id)
