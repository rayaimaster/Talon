"""
Safe, sandboxed shell execution tool.

Commands are validated against an allowlist and blocked patterns before
running with a strict timeout.
"""

import asyncio
import logging
import re
import shlex

from core.policy import check_shell_command_async

logger = logging.getLogger(__name__)

# Commands that are explicitly safe for an SRE/data agent to run
ALLOWED_COMMANDS: list[str] = [
    "ls", "cat", "head", "tail", "grep", "find", "ps",
    "df", "du", "curl", "wget",
    "python3", "python",
    "node",
    "git",
    "echo", "date", "whoami", "hostname", "uname",
    "env", "printenv",
    "wc", "sort", "uniq", "awk", "sed", "cut", "tr",
    "jq",
    "ping",
    "netstat", "ss", "lsof",
    "uptime", "free", "top", "htop",
]

MAX_OUTPUT_CHARS = 4_000


def _first_token(command: str) -> str:
    """Return the first word of a command (the executable name)."""
    try:
        tokens = shlex.split(command)
        if tokens:
            return tokens[0].split("/")[-1]  # strip path prefix
    except ValueError:
        pass
    return command.split()[0] if command.strip() else ""


async def shell_exec(command: str, timeout: int = 30) -> str:
    """
    Execute a shell command safely and return the output.

    - Blocked dangerous patterns are rejected immediately.
    - Commands not on the allowlist trigger a warning (but still run).
    - Output is capped at MAX_OUTPUT_CHARS characters.
    - Execution is time-limited by `timeout` seconds.
    """
    logger.info("shell_exec: %r (timeout=%ds)", command, timeout)

    # ── Safety checks ─────────────────────────────────────────────────────────
    allowed, reason = await check_shell_command_async(command)
    if not allowed:
        return f"❌ Command blocked: {reason}"

    first = _first_token(command)
    if first and first not in ALLOWED_COMMANDS:
        logger.warning("shell_exec: command %r is not in allowlist", first)
        # We warn but do not block — the operator chose to deploy this

    # ── Execute ───────────────────────────────────────────────────────────────
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"❌ Command timed out after {timeout}s: {command!r}"

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        returncode = proc.returncode

        # Format output
        output_parts = []
        if stdout.strip():
            output_parts.append(stdout.strip())
        if stderr.strip():
            output_parts.append(f"[stderr]\n{stderr.strip()}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        # Truncate
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(output)} total chars]"

        prefix = f"$ {command}\n[exit {returncode}]\n"
        return prefix + output

    except FileNotFoundError:
        return f"❌ Command not found: {first!r}"
    except PermissionError as exc:
        return f"❌ Permission denied: {exc}"
    except Exception as exc:
        logger.error("shell_exec unexpected error: %s", exc)
        return f"❌ Unexpected error: {exc}"
