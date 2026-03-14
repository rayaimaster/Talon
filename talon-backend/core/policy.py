"""
Configurable policy / safety checks for Project Talon.

Policies are persisted in SQLite and cached in memory. Evaluation can
run either through the legacy local regex engine or through OPA/Rego
when POLICY_ENGINE=opa and OPA_BASE_URL is configured.
"""

import json
import logging
import os
import re
import time
from copy import deepcopy
from typing import Any, Optional

import httpx

from core import memory

logger = logging.getLogger(__name__)


DEFAULT_POLICY_RULES: list[dict[str, Any]] = [
    {
        "id": "msg-hacking",
        "name": "Block hacking requests",
        "scope": "message",
        "pattern": r"how to hack",
        "action": "block",
        "description": "Prevents direct hacking instructions.",
        "enabled": True,
        "priority": 10,
    },
    {
        "id": "msg-malware",
        "name": "Block malware content",
        "scope": "message",
        "pattern": r"ransomware|keylogger|malware|phishing template|ddos",
        "action": "block",
        "description": "Blocks clearly malicious content requests.",
        "enabled": True,
        "priority": 20,
    },
    {
        "id": "shell-rm-root",
        "name": "Block destructive rm -rf",
        "scope": "shell",
        "pattern": r"rm\s+-rf\s+/",
        "action": "block",
        "description": "Prevents destructive filesystem deletion.",
        "enabled": True,
        "priority": 10,
    },
    {
        "id": "shell-fork-bomb",
        "name": "Block fork bombs",
        "scope": "shell",
        "pattern": r":\(\)\s*\{",
        "action": "block",
        "description": "Prevents shell fork bomb execution.",
        "enabled": True,
        "priority": 20,
    },
    {
        "id": "shell-dev-write",
        "name": "Block raw device writes",
        "scope": "shell",
        "pattern": r"mkfs|>\s*/dev/|dd\s+if=|chmod\s+777\s+/",
        "action": "block",
        "description": "Blocks destructive raw-device and privilege patterns.",
        "enabled": True,
        "priority": 30,
    },
    {
        "id": "shell-pipe-sh",
        "name": "Block curl or wget pipe to shell",
        "scope": "shell",
        "pattern": r"(wget|curl).*\|\s*sh",
        "action": "block",
        "description": "Prevents piping downloaded scripts directly into a shell.",
        "enabled": True,
        "priority": 40,
    },
    {
        "id": "shell-sensitive-files",
        "name": "Block sensitive file access",
        "scope": "shell",
        "pattern": r"/etc/shadow|/etc/passwd|sudo\s+su",
        "action": "block",
        "description": "Prevents access to sensitive system files and privilege escalation shortcuts.",
        "enabled": True,
        "priority": 50,
    },
]

_POLICY_RULES_CACHE: list[dict[str, Any]] = []
_POLICY_RULES_CACHE_LOADED_AT: float = 0.0

DEFAULT_OPA_POLICY_ID = "talon"
DEFAULT_OPA_POLICY_PACKAGE = "talon"
DEFAULT_OPA_DECISION_PATH = "/v1/data/talon/decision"
DEFAULT_OPA_POLICY_MODULE = """
package talon

default decision = {"allowed": true, "reason": "", "matched_rules": []}

decision = {"allowed": false, "reason": concat("; ", reasons), "matched_rules": matched} {
  blocked := [rule |
    rule := data.talon.policy_rules[_];
    rule.enabled == true;
    rule.scope == input.scope;
    re_match(rule.pattern, input.text);
    rule.action == "block"
  ]
  count(blocked) > 0
  reasons := [sprintf("%s: %s", [rule.name, rule.description]) | rule := blocked[_]]
  matched := [rule.id | rule := blocked[_]]
}
""".strip()


async def ensure_policy_rules() -> None:
    """Seed default rules into the database if they do not yet exist."""
    existing = {rule["id"] for rule in await memory.list_policy_rules()}
    for rule in DEFAULT_POLICY_RULES:
        if rule["id"] in existing:
            continue
        await memory.upsert_policy_rule(
            rule_id=rule["id"],
            name=rule["name"],
            scope=rule["scope"],
            pattern=rule["pattern"],
            action=rule["action"],
            description=rule["description"],
            enabled=rule["enabled"],
            priority=rule["priority"],
        )


async def refresh_policy_cache() -> list[dict[str, Any]]:
    """Reload the active rule cache from the database."""
    global _POLICY_RULES_CACHE, _POLICY_RULES_CACHE_LOADED_AT
    _POLICY_RULES_CACHE = await memory.list_policy_rules()
    _POLICY_RULES_CACHE_LOADED_AT = time.time()
    logger.info("Loaded %d policy rules", len(_POLICY_RULES_CACHE))
    if get_policy_engine() == "opa":
        await sync_opa_bundle()
    return get_policy_rules_snapshot()


def get_policy_rules_snapshot() -> list[dict[str, Any]]:
    """Return a copy of the cached rules for API/UI use."""
    if _POLICY_RULES_CACHE:
        return deepcopy(_POLICY_RULES_CACHE)
    return deepcopy(DEFAULT_POLICY_RULES)


def _enabled_rules_for_scope(scope: str) -> list[dict[str, Any]]:
    source = _POLICY_RULES_CACHE or DEFAULT_POLICY_RULES
    return [
        rule for rule in source
        if rule.get("enabled") and rule.get("scope") == scope
    ]


def _evaluate_scope(scope: str, text: str) -> tuple[bool, str]:
    for rule in _enabled_rules_for_scope(scope):
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        try:
            if re.search(pattern, text, re.IGNORECASE):
                reason = f"{rule.get('name', rule.get('id', 'policy-rule'))}: {rule.get('description', pattern)}"
                logger.warning(
                    "Policy block: scope=%s rule=%s text=%s",
                    scope,
                    rule.get("id"),
                    text[:200],
                )
                return False, reason
        except re.error as exc:
            logger.error("Invalid policy regex for rule %s: %s", rule.get("id"), exc)
    return True, ""


def get_policy_engine() -> str:
    engine = os.environ.get("POLICY_ENGINE", "legacy").strip().lower()
    if engine in {"legacy", "opa"}:
        return engine
    logger.warning("Unknown POLICY_ENGINE=%r. Falling back to legacy.", engine)
    return "legacy"


def get_policy_status() -> dict[str, str]:
    engine = get_policy_engine()
    if engine == "legacy":
        return {
            "engine": "legacy",
            "status": "configured",
            "detail": "Using the in-process policy evaluator.",
        }

    opa_base_url = os.environ.get("OPA_BASE_URL", "").strip()
    if not opa_base_url:
        return {
            "engine": "opa",
            "status": "misconfigured",
            "detail": "OPA_BASE_URL is required when POLICY_ENGINE=opa.",
        }

    fail_mode = _get_opa_fail_mode()
    return {
        "engine": "opa",
        "status": "configured",
        "detail": f"OPA evaluation enabled via {opa_base_url} (fail mode: {fail_mode}).",
    }


def _get_opa_fail_mode() -> str:
    raw = os.environ.get("OPA_FAIL_MODE", "closed").strip().lower()
    if raw in {"closed", "open"}:
        return raw
    logger.warning("Unknown OPA_FAIL_MODE=%r. Falling back to closed.", raw)
    return "closed"


def _get_opa_base_url() -> str:
    return os.environ.get("OPA_BASE_URL", "").strip().rstrip("/")


async def sync_opa_bundle() -> dict[str, Any]:
    status = get_policy_status()
    if status["engine"] != "opa":
        return {"synced": False, "status": "legacy"}
    if status["status"] != "configured":
        raise RuntimeError(status["detail"])

    rules = get_policy_rules_snapshot()
    base_url = _get_opa_base_url()

    async with httpx.AsyncClient(timeout=10) as client:
        policy_resp = await client.put(
            f"{base_url}/v1/policies/{DEFAULT_OPA_POLICY_ID}",
            content=DEFAULT_OPA_POLICY_MODULE,
            headers={"Content-Type": "text/plain"},
        )
        policy_resp.raise_for_status()

        data_resp = await client.put(
            f"{base_url}/v1/data/talon",
            json={"policy_rules": rules},
        )
        data_resp.raise_for_status()

    logger.info("OPA bundle synced with %d policy rules", len(rules))
    return {
        "synced": True,
        "engine": "opa",
        "rule_count": len(rules),
        "policy_id": DEFAULT_OPA_POLICY_ID,
    }


async def _evaluate_scope_async(scope: str, text: str) -> tuple[bool, str]:
    if get_policy_engine() != "opa":
        return _evaluate_scope(scope, text)

    status = get_policy_status()
    if status["status"] != "configured":
        return _handle_opa_failure(status["detail"])

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_get_opa_base_url()}{DEFAULT_OPA_DECISION_PATH}",
                json={"input": {"scope": scope, "text": text}},
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.error("OPA policy evaluation failed: %s", exc)
        return _handle_opa_failure(str(exc))

    result = payload.get("result") or {}
    allowed = bool(result.get("allowed", True))
    reason = str(result.get("reason", ""))
    if not allowed:
        logger.warning(
            "OPA policy block: scope=%s matched_rules=%s text=%s",
            scope,
            json.dumps(result.get("matched_rules", []), default=str),
            text[:200],
        )
    return allowed, reason


def _handle_opa_failure(reason: str) -> tuple[bool, str]:
    if _get_opa_fail_mode() == "open":
        logger.warning("OPA evaluation failed open: %s", reason)
        return True, ""
    logger.warning("OPA evaluation failed closed: %s", reason)
    return False, f"OPA policy evaluation failed: {reason}"


def check_message(text: str) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    allowed=True means the message is fine to process.
    """
    return _evaluate_scope("message", text)


async def check_message_async(text: str) -> tuple[bool, str]:
    return await _evaluate_scope_async("message", text)


def check_shell_command(command: str) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    allowed=True means the command is safe to run.
    """
    return _evaluate_scope("shell", command)


async def check_shell_command_async(command: str) -> tuple[bool, str]:
    return await _evaluate_scope_async("shell", command)


def check_tool_call(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """
    Gate tool calls before execution.
    """
    allowed, reason = _evaluate_scope(f"tool:{tool_name}", str(tool_input))
    if not allowed:
        return allowed, reason
    if tool_name == "shell_exec":
        cmd = tool_input.get("command", "")
        return check_shell_command(cmd)
    return True, ""


async def check_tool_call_async(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    allowed, reason = await _evaluate_scope_async(f"tool:{tool_name}", json.dumps(tool_input, default=str))
    if not allowed:
        return allowed, reason
    if tool_name == "shell_exec":
        cmd = tool_input.get("command", "")
        return await check_shell_command_async(cmd)
    return True, ""
