"""
Microsoft Teams Bot Framework connector.

Handles the incoming webhook from Azure Bot Service and sends replies
back to Teams via the Bot Framework REST API.

Security:
  - Bot Framework JWT bearer token validation against Microsoft's JWKS
  - Set SKIP_SIGNATURE_VERIFICATION=true for local testing
"""

import json
import logging
import os
import re
import time
from typing import Optional

import httpx
import jwt
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from channels.router import extract_mention, get_all_agents, route_message
from core import audit, memory
from core.react_loop import get_react_loop

logger = logging.getLogger(__name__)
router = APIRouter()

BOT_FRAMEWORK_OPENID_CONFIG_URL = (
    "https://login.botframework.com/v1/.well-known/openidconfiguration"
)
DEFAULT_METADATA_TTL_SECONDS = 3600
_openid_config_cache: dict[str, object] = {"value": None, "expires_at": 0.0}
_jwks_cache: dict[str, object] = {"keys": {}, "expires_at": 0.0, "jwks_uri": ""}


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/api/messages")
async def teams_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    """
    Microsoft Bot Framework webhook endpoint.

    Receives Activity objects from Teams and dispatches them to the
    appropriate agent for processing.
    """
    raw_body = await request.body()

    # ── Signature verification ────────────────────────────────────────────────
    if not _skip_sig_verification():
        auth_header = request.headers.get("Authorization", "")
        if not await _verify_bot_framework_auth(auth_header):
            logger.warning("Teams webhook: invalid auth header")
            raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    activity_type = body.get("type", "")
    logger.debug("Teams activity: type=%s", activity_type)

    if activity_type == "message":
        background_tasks.add_task(_handle_message_activity, body)

    elif activity_type == "conversationUpdate":
        # Bot added to channel — send a greeting
        background_tasks.add_task(_handle_conversation_update, body)

    return {"status": "ok"}


# ── Activity handlers ─────────────────────────────────────────────────────────

async def _handle_message_activity(body: dict) -> None:
    """Process a Teams message and send the agent's reply."""
    text_raw = body.get("text", "").strip()
    if not text_raw:
        return

    # Extract sender info
    from_info = body.get("from", {})
    user_id = from_info.get("id", "unknown")
    user_name = from_info.get("name", "User")

    # Conversation / channel info
    conversation = body.get("conversation", {})
    conversation_id = conversation.get("id", "unknown")
    channel_data = body.get("channelData", {})
    channel_name = ""
    if isinstance(channel_data, dict):
        channel_obj = channel_data.get("channel", {})
        if isinstance(channel_obj, dict):
            channel_name = channel_obj.get("name", "")

    # Activity metadata for reply
    service_url = body.get("serviceUrl", "")
    activity_id = body.get("id", "")
    bot_name = (body.get("recipient") or {}).get("name", "")

    # Clean the text and extract @mentions
    text_clean, mentioned_agent = extract_mention(text_raw, bot_name=bot_name)
    if not text_clean:
        return  # Empty after stripping mentions

    logger.info(
        "Teams message: user=%s channel=%s conv=%s text=%r",
        user_name, channel_name, conversation_id[:20], text_clean[:100],
    )

    # Route to agent
    agent_config = route_message(
        text=text_clean,
        channel_name=channel_name,
        mentioned_agent=mentioned_agent,
    )

    if agent_config is None:
        logger.warning("No agent matched for message; dropping")
        return

    # Check agent status
    agent_id = agent_config["id"]
    kill_switch = await memory.get_kill_switch_state()
    if kill_switch["active"]:
        await audit.log_event(
            agent_id=agent_id,
            event_type="message_dropped",
            user_id=user_id,
            conversation_id=conversation_id,
            details={"reason": "kill_switch", "text": text_clean[:200]},
        )
        if service_url and conversation_id:
            await send_teams_reply(
                service_url=service_url,
                conversation_id=conversation_id,
                activity_id=activity_id,
                text=(
                    "⛔ The global kill switch is active. "
                    f"{kill_switch.get('reason') or 'New work is currently halted.'}"
                ),
            )
        return

    status = await memory.get_agent_status(agent_id)
    if status == "paused":
        await audit.log_event(
            agent_id=agent_id,
            event_type="message_dropped",
            user_id=user_id,
            conversation_id=conversation_id,
            details={"reason": "agent paused", "text": text_clean[:200]},
        )
        # Optionally reply with a "I'm paused" message
        if service_url and conversation_id:
            await send_teams_reply(
                service_url=service_url,
                conversation_id=conversation_id,
                activity_id=activity_id,
                text=f"⏸️ {agent_config.get('name', 'Agent')} is currently paused.",
            )
        return

    # Run the ReAct loop
    react = get_react_loop()
    try:
        response_text = await react.run(
            agent_config=agent_config,
            message=text_clean,
            conversation_id=conversation_id,
            user_id=user_id,
        )
    except Exception as exc:
        logger.error("[%s] ReAct loop error: %s", agent_id, exc, exc_info=True)
        response_text = f"⚠️ I encountered an error processing your request: {exc}"

    # Send reply back to Teams
    if service_url and conversation_id:
        await send_teams_reply(
            service_url=service_url,
            conversation_id=conversation_id,
            activity_id=activity_id,
            text=response_text,
        )
    else:
        logger.info("No service_url — response: %s", response_text[:200])


async def _handle_conversation_update(body: dict) -> None:
    """Handle bot being added to a channel."""
    members_added = body.get("membersAdded", [])
    bot_id = (body.get("recipient") or {}).get("id", "")
    service_url = body.get("serviceUrl", "")
    conversation_id = (body.get("conversation") or {}).get("id", "")
    activity_id = body.get("id", "")

    for member in members_added:
        if member.get("id") == bot_id:
            # Bot was added — send a greeting
            agents = list(get_all_agents().values())
            agent_names = ", ".join(
                f"{a.get('emoji', '')} **{a.get('name')}** ({a.get('role')})"
                for a in agents
            )
            greeting = (
                "👋 Hello! I'm the **Project Talon** Digital Employee Platform.\n\n"
                f"Available agents: {agent_names}\n\n"
                "You can @mention an agent by name, or just ask your question "
                "and I'll route it to the right person."
            )
            if service_url and conversation_id:
                await send_teams_reply(
                    service_url=service_url,
                    conversation_id=conversation_id,
                    activity_id=activity_id,
                    text=greeting,
                )


# ── Reply sender ──────────────────────────────────────────────────────────────

async def send_teams_reply(
    service_url: str,
    conversation_id: str,
    activity_id: str,
    text: str,
    bot_token: Optional[str] = None,
) -> None:
    """
    Send a reply back to Microsoft Teams via the Bot Framework REST API.

    If no bot_token is provided, attempts to obtain one using the
    TEAMS_APP_ID / TEAMS_APP_PASSWORD credentials.
    """
    if not service_url or not conversation_id:
        logger.warning("send_teams_reply: missing service_url or conversation_id")
        return

    if bot_token is None:
        bot_token = await _get_bot_token()

    if not bot_token:
        # Local testing mode — just log the response
        logger.info(
            "[LOCAL MODE] Would reply to Teams:\n  conv=%s\n  text=%s",
            conversation_id[:30], text[:300],
        )
        return

    reply_activity = {
        "type": "message",
        "text": text,
        "conversation": {"id": conversation_id},
        "replyToId": activity_id,
    }

    url = (
        f"{service_url.rstrip('/')}/v3/conversations/"
        f"{conversation_id}/activities/{activity_id}"
    )

    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=reply_activity, headers=headers)
            resp.raise_for_status()
            logger.debug("Teams reply sent: status=%d", resp.status_code)
    except httpx.HTTPStatusError as exc:
        logger.error("Teams reply HTTP error: %s — %s", exc, exc.response.text[:200])
    except Exception as exc:
        logger.error("Teams reply failed: %s", exc)


async def _get_bot_token() -> Optional[str]:
    """Obtain an OAuth 2.0 token from Microsoft for the Bot Framework."""
    app_id = os.environ.get("TEAMS_APP_ID", "")
    app_password = os.environ.get("TEAMS_APP_PASSWORD", "")

    if not app_id or not app_password:
        return None  # Local mode

    token_url = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": app_id,
        "client_secret": app_password,
        "scope": "https://api.botframework.com/.default",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(token_url, data=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("access_token")
    except Exception as exc:
        logger.error("Failed to get Bot Framework token: %s", exc)
        return None


# ── Security ──────────────────────────────────────────────────────────────────

def _skip_sig_verification() -> bool:
    return os.environ.get("SKIP_SIGNATURE_VERIFICATION", "").lower() in ("true", "1", "yes")


async def _verify_bot_framework_auth(auth_header: str) -> bool:
    """Verify the Bot Framework JWT bearer token."""
    if not auth_header.startswith("Bearer "):
        return False

    app_id = os.environ.get("TEAMS_APP_ID", "").strip()
    if not app_id:
        logger.warning("Teams webhook auth rejected: TEAMS_APP_ID is not configured")
        return False

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return False

    try:
        return await _validate_bot_framework_token(token=token, app_id=app_id)
    except Exception as exc:
        logger.warning("Teams webhook auth validation failed: %s", exc)
        return False


async def _validate_bot_framework_token(token: str, app_id: str) -> bool:
    """Validate issuer, audience, expiry, and signature for Bot Framework tokens."""
    header = jwt.get_unverified_header(token)
    alg = header.get("alg")
    kid = header.get("kid")

    if alg != "RS256" or not kid:
        raise ValueError("Unsupported Bot Framework token header")

    openid_config = await _get_bot_framework_openid_config()
    jwk = await _get_bot_framework_signing_key(kid, openid_config["jwks_uri"])
    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))

    payload = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience=app_id,
        options={"require": ["exp", "iat", "iss", "aud"]},
        leeway=300,
    )

    issuer = payload.get("iss", "")
    if issuer not in _get_allowed_bot_framework_issuers(openid_config):
        raise ValueError(f"Unexpected Bot Framework issuer: {issuer}")

    return True


async def _get_bot_framework_openid_config() -> dict:
    cached = _openid_config_cache.get("value")
    expires_at = float(_openid_config_cache.get("expires_at", 0.0))
    now = time.time()
    if cached and now < expires_at:
        return cached  # type: ignore[return-value]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(BOT_FRAMEWORK_OPENID_CONFIG_URL)
        resp.raise_for_status()
        payload = resp.json()
        ttl = _get_cache_ttl_seconds(resp.headers)

    _openid_config_cache["value"] = payload
    _openid_config_cache["expires_at"] = now + ttl
    return payload


async def _get_bot_framework_signing_key(kid: str, jwks_uri: str) -> dict:
    now = time.time()
    cached_uri = str(_jwks_cache.get("jwks_uri", ""))
    cached_keys = _jwks_cache.get("keys", {})
    expires_at = float(_jwks_cache.get("expires_at", 0.0))

    if cached_uri != jwks_uri or not cached_keys or now >= expires_at or kid not in cached_keys:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            payload = resp.json()
            ttl = _get_cache_ttl_seconds(resp.headers)

        key_map = {
            key["kid"]: key
            for key in payload.get("keys", [])
            if isinstance(key, dict) and key.get("kid")
        }
        _jwks_cache["jwks_uri"] = jwks_uri
        _jwks_cache["keys"] = key_map
        _jwks_cache["expires_at"] = now + ttl
        cached_keys = key_map

    key = cached_keys.get(kid)
    if not key:
        raise ValueError(f"Bot Framework signing key not found for kid={kid}")
    return key


def _get_allowed_bot_framework_issuers(openid_config: dict) -> set[str]:
    issuers = {"https://api.botframework.com", "https://api.botframework.com/"}
    issuer = openid_config.get("issuer")
    if isinstance(issuer, str) and issuer.strip():
        issuers.add(issuer)
        issuers.add(issuer.rstrip("/"))
        issuers.add(f"{issuer.rstrip('/')}/")
    return issuers


def _get_cache_ttl_seconds(headers: httpx.Headers) -> int:
    cache_control = headers.get("Cache-Control", "")
    match = re.search(r"max-age=(\d+)", cache_control)
    if match:
        return max(int(match.group(1)), 60)
    return DEFAULT_METADATA_TTL_SECONDS
