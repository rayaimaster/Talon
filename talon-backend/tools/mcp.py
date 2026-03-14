"""
Model Context Protocol (MCP) integration for Project Talon.

MCP servers are configured through MCP_SERVERS_JSON. Talon currently supports
stdio MCP servers and discovers their tools at startup, then exposes those
tools through the existing registry / ReAct loop.

Example MCP_SERVERS_JSON value:

{
  "filesystem": {
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  }
}
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shlex
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

CLIENT_NAME = "project-talon"
CLIENT_VERSION = "2.0.0"
MCP_PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TOOL_TIMEOUT = 30

_MCP_TOOL_CACHE: dict[str, dict[str, Any]] = {}
_MCP_STATUS_CACHE: dict[str, Any] = {
    "status": "disabled",
    "servers_configured": 0,
    "discovered_tools": 0,
    "detail": "MCP is disabled. Set MCP_SERVERS_JSON to enable MCP servers.",
    "servers": {},
}


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    cwd: str
    timeout: int


class MCPError(RuntimeError):
    """Raised for MCP transport, protocol, or configuration failures."""


def _sanitize_segment(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "tool"


def _stable_talon_tool_name(server_name: str, tool_name: str) -> str:
    server_part = _sanitize_segment(server_name)[:18]
    tool_part = _sanitize_segment(tool_name)[:24]
    digest = hashlib.sha1(f"{server_name}:{tool_name}".encode("utf-8")).hexdigest()[:8]
    return f"mcp__{server_part}__{tool_part}__{digest}"


def _default_input_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "required": []}


def _get_timeout_value(raw: Any, default: int = DEFAULT_TOOL_TIMEOUT) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(5, min(value, 120))


def _get_default_timeout() -> int:
    return _get_timeout_value(os.environ.get("MCP_TOOL_TIMEOUT", DEFAULT_TOOL_TIMEOUT))


def _load_server_configs() -> tuple[list[MCPServerConfig], list[str]]:
    raw = os.environ.get("MCP_SERVERS_JSON", "").strip()
    if not raw:
        return [], []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], [f"MCP_SERVERS_JSON is not valid JSON: {exc}"]

    entries: list[dict[str, Any]] = []
    if isinstance(parsed, dict):
        if "command" in parsed and "name" in parsed:
            entries = [parsed]
        else:
            for name, config in parsed.items():
                if not isinstance(config, dict):
                    return [], [f"MCP server entry {name!r} must be a JSON object."]
                entry = dict(config)
                entry.setdefault("name", str(name))
                entries.append(entry)
    elif isinstance(parsed, list):
        for idx, item in enumerate(parsed):
            if not isinstance(item, dict):
                return [], [f"MCP server entry #{idx + 1} must be a JSON object."]
            entries.append(dict(item))
    else:
        return [], ["MCP_SERVERS_JSON must be a JSON object or array."]

    configs: list[MCPServerConfig] = []
    errors: list[str] = []
    for entry in entries:
        name = str(entry.get("name", "")).strip()
        if not name:
            errors.append("Every MCP server entry must include a non-empty name.")
            continue

        transport = str(entry.get("transport", "stdio")).strip().lower()
        if transport != "stdio":
            errors.append(
                f"MCP server {name!r} uses unsupported transport {transport!r}. "
                "Only stdio is supported right now."
            )
            continue

        command_value = entry.get("command", "")
        if isinstance(command_value, str):
            command_parts = shlex.split(command_value)
        else:
            command_parts = []
        args_value = entry.get("args", [])
        if args_value and not isinstance(args_value, list):
            errors.append(f"MCP server {name!r} has non-list args.")
            continue
        args = [str(part) for part in (args_value or [])]

        if not command_parts:
            errors.append(f"MCP server {name!r} is missing a command.")
            continue

        if len(command_parts) > 1 and args:
            errors.append(
                f"MCP server {name!r} should provide either a split command or args, not both."
            )
            continue

        env_value = entry.get("env", {})
        if env_value and not isinstance(env_value, dict):
            errors.append(f"MCP server {name!r} has non-object env.")
            continue

        command = command_parts[0]
        full_args = command_parts[1:] + args
        configs.append(
            MCPServerConfig(
                name=name,
                command=command,
                args=full_args,
                env={str(k): str(v) for k, v in (env_value or {}).items()},
                cwd=str(entry.get("cwd", "")).strip(),
                timeout=_get_timeout_value(entry.get("timeout"), _get_default_timeout()),
            )
        )

    return configs, errors


def get_mcp_status() -> dict[str, Any]:
    """Return a copy of the current MCP status snapshot."""
    return deepcopy(_MCP_STATUS_CACHE)


def list_mcp_tools() -> list[str]:
    return list(_MCP_TOOL_CACHE.keys())


def _resolve_requested_mcp_tools(requested_tools: list[str]) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()

    for requested in requested_tools:
        matches: list[str] = []

        if requested == "mcp:*":
            matches = list(_MCP_TOOL_CACHE.keys())
        elif requested.startswith("mcp:") and requested.endswith(":*"):
            server_name = requested[4:-2]
            matches = [
                tool_name
                for tool_name, meta in _MCP_TOOL_CACHE.items()
                if meta.get("server_name") == server_name
            ]
        elif requested.startswith("mcp:") and requested.count(":") >= 2:
            _, server_name, original_tool_name = requested.split(":", 2)
            for tool_name, meta in _MCP_TOOL_CACHE.items():
                if (
                    meta.get("server_name") == server_name
                    and meta.get("original_tool_name") == original_tool_name
                ):
                    matches = [tool_name]
                    break
        elif requested in _MCP_TOOL_CACHE:
            matches = [requested]

        for match in matches:
            if match not in seen:
                resolved.append(match)
                seen.add(match)

    return resolved


def get_mcp_tool_definitions(requested_tools: list[str]) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for tool_name in _resolve_requested_mcp_tools(requested_tools):
        meta = _MCP_TOOL_CACHE.get(tool_name)
        if meta:
            definitions.append(deepcopy(meta["tool_definition"]))
    return definitions


class _MCPStdioClient:
    def __init__(self, config: MCPServerConfig):
        self._config = config
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._next_id = 1

    async def __aenter__(self) -> "_MCPStdioClient":
        env = os.environ.copy()
        env.update(self._config.env)
        self._proc = await asyncio.create_subprocess_exec(
            self._config.command,
            *self._config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self._config.cwd or None,
        )
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if not self._proc:
            return
        if self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()

    async def initialize(self) -> None:
        await self.request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        )
        await self.notify("notifications/initialized", {})

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send_message({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        await self._send_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )

        while True:
            message = await self._read_message()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise MCPError(
                    f"MCP request {method!r} failed: {error.get('message', error)}"
                )
            result = message.get("result")
            if not isinstance(result, dict):
                return {"value": result}
            return result

    async def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = await self.request("tools/list", params)
            batch = result.get("tools", [])
            if isinstance(batch, list):
                tools.extend(item for item in batch if isinstance(item, dict))
            cursor = result.get("nextCursor") or result.get("next_cursor")
            if not cursor:
                break
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )

    async def _send_message(self, payload: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise MCPError("MCP process is not running.")
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)
        await self._proc.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        if not self._proc or not self._proc.stdout:
            raise MCPError("MCP process is not running.")

        headers: dict[str, str] = {}
        while True:
            line = await asyncio.wait_for(
                self._proc.stdout.readline(),
                timeout=self._config.timeout,
            )
            if not line:
                stderr = await self._read_stderr()
                raise MCPError(
                    f"MCP server {self._config.name!r} closed the stdio stream unexpectedly."
                    + (f" stderr: {stderr}" if stderr else "")
                )
            if line in {b"\r\n", b"\n"}:
                break
            try:
                decoded = line.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise MCPError(f"Invalid MCP header from {self._config.name!r}: {exc}") from exc
            if ":" not in decoded:
                raise MCPError(f"Malformed MCP header from {self._config.name!r}: {decoded!r}")
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        try:
            content_length = int(headers["content-length"])
        except (KeyError, ValueError) as exc:
            raise MCPError(
                f"MCP response from {self._config.name!r} is missing a valid Content-Length header."
            ) from exc

        body = await asyncio.wait_for(
            self._proc.stdout.readexactly(content_length),
            timeout=self._config.timeout,
        )
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MCPError(f"Invalid MCP JSON from {self._config.name!r}: {exc}") from exc

    async def _read_stderr(self) -> str:
        if not self._proc or not self._proc.stderr:
            return ""
        try:
            await asyncio.sleep(0)
            chunks = []
            while True:
                chunk = await asyncio.wait_for(self._proc.stderr.read(1024), timeout=0.05)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", errors="replace").strip()
        except Exception:
            return ""


async def _discover_server_tools(config: MCPServerConfig) -> list[dict[str, Any]]:
    async with _MCPStdioClient(config) as client:
        return await client.list_tools()


def _normalise_input_schema(schema: Any) -> dict[str, Any]:
    if isinstance(schema, dict) and schema.get("type") == "object":
        normalized = deepcopy(schema)
        normalized.setdefault("properties", {})
        normalized.setdefault("required", [])
        return normalized
    return _default_input_schema()


async def refresh_mcp_tools() -> dict[str, Any]:
    """Discover tools from configured MCP servers and refresh the in-memory cache."""
    global _MCP_TOOL_CACHE, _MCP_STATUS_CACHE

    _MCP_TOOL_CACHE = {}
    configs, config_errors = _load_server_configs()
    server_status: dict[str, Any] = {}

    if not configs and not config_errors:
        _MCP_STATUS_CACHE = {
            "status": "disabled",
            "servers_configured": 0,
            "discovered_tools": 0,
            "detail": "MCP is disabled. Set MCP_SERVERS_JSON to enable MCP servers.",
            "servers": {},
        }
        return get_mcp_status()

    successes = 0
    failures = 0

    for error in config_errors:
        logger.warning("MCP configuration: %s", error)

    for config in configs:
        try:
            raw_tools = await _discover_server_tools(config)
            tool_count = 0
            for raw_tool in raw_tools:
                original_tool_name = str(raw_tool.get("name", "")).strip()
                if not original_tool_name:
                    continue
                talon_tool_name = _stable_talon_tool_name(config.name, original_tool_name)
                description = str(raw_tool.get("description", "")).strip()
                if not description:
                    description = f"MCP tool {original_tool_name!r} from server {config.name!r}."
                schema = _normalise_input_schema(raw_tool.get("inputSchema") or raw_tool.get("input_schema"))
                _MCP_TOOL_CACHE[talon_tool_name] = {
                    "server_name": config.name,
                    "server_config": config,
                    "original_tool_name": original_tool_name,
                    "tool_definition": {
                        "name": talon_tool_name,
                        "description": f"[MCP:{config.name}] {description}",
                        "input_schema": schema,
                    },
                }
                tool_count += 1

            server_status[config.name] = {
                "status": "configured",
                "transport": "stdio",
                "command": config.command,
                "discovered_tools": tool_count,
            }
            successes += 1
        except Exception as exc:
            failures += 1
            logger.warning("MCP server %s discovery failed: %s", config.name, exc)
            server_status[config.name] = {
                "status": "error",
                "transport": "stdio",
                "command": config.command,
                "detail": str(exc),
                "discovered_tools": 0,
            }

    if config_errors and not successes and not configs:
        status = "misconfigured"
    elif successes and failures:
        status = "degraded"
    elif successes:
        status = "configured"
    else:
        status = "misconfigured"

    if status == "configured":
        detail = f"Discovered {len(_MCP_TOOL_CACHE)} MCP tool(s) across {successes} server(s)."
    elif status == "degraded":
        detail = (
            f"Discovered {len(_MCP_TOOL_CACHE)} MCP tool(s), but {failures} server(s) failed "
            "or returned no usable tools."
        )
    else:
        detail = "No MCP tools were discovered. Check MCP_SERVERS_JSON and server commands."

    if config_errors:
        detail = f"{detail} Config issues: {'; '.join(config_errors)}"

    _MCP_STATUS_CACHE = {
        "status": status,
        "servers_configured": len(configs),
        "discovered_tools": len(_MCP_TOOL_CACHE),
        "detail": detail,
        "servers": server_status,
    }
    return get_mcp_status()


def _lookup_mcp_tool(tool_name: str) -> Optional[dict[str, Any]]:
    if tool_name in _MCP_TOOL_CACHE:
        return _MCP_TOOL_CACHE[tool_name]

    if tool_name.startswith("mcp:") and tool_name.count(":") >= 2:
        _, server_name, original_tool_name = tool_name.split(":", 2)
        for meta in _MCP_TOOL_CACHE.values():
            if (
                meta.get("server_name") == server_name
                and meta.get("original_tool_name") == original_tool_name
            ):
                return meta
    return None


def _format_tool_result(server_name: str, original_tool_name: str, result: dict[str, Any]) -> str:
    content = result.get("content", [])
    text_parts: list[str] = []

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    text_parts.append(text)
            elif isinstance(item, dict):
                text_parts.append(json.dumps(item, indent=2, sort_keys=True, default=str))
            elif item is not None:
                text_parts.append(str(item))
    elif content:
        text_parts.append(str(content))

    if not text_parts and result.get("structuredContent") is not None:
        text_parts.append(
            json.dumps(result.get("structuredContent"), indent=2, sort_keys=True, default=str)
        )

    if not text_parts:
        text_parts.append("(no output)")

    prefix = f"[MCP {server_name}:{original_tool_name}]"
    if result.get("isError"):
        prefix = f"❌ {prefix}"

    return prefix + "\n" + "\n".join(part for part in text_parts if part)


async def execute_mcp_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    meta = _lookup_mcp_tool(tool_name)
    if meta is None:
        status = get_mcp_status()
        if status["status"] == "disabled":
            return "❌ MCP is disabled. Set MCP_SERVERS_JSON to enable MCP-backed tools."
        return f"❌ Unknown MCP tool: {tool_name!r}"

    config: MCPServerConfig = meta["server_config"]
    try:
        async with _MCPStdioClient(config) as client:
            result = await client.call_tool(meta["original_tool_name"], tool_input)
        return _format_tool_result(
            meta["server_name"],
            meta["original_tool_name"],
            result,
        )
    except Exception as exc:
        logger.error(
            "MCP tool call failed server=%s tool=%s error=%s",
            meta["server_name"],
            meta["original_tool_name"],
            exc,
        )
        return (
            f"❌ MCP tool call failed for {meta['server_name']}:{meta['original_tool_name']}: {exc}"
        )
