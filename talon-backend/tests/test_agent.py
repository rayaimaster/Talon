"""
Basic tests for Project Talon.

Run with:
    cd /workspace/talon-backend
    pip install pytest pytest-asyncio httpx
    pytest tests/ -v

These tests cover:
  - Memory layer (SQLite CRUD)
  - Tool execution (datetime, shell, web_search)
  - Policy checks
  - Router logic
  - API endpoints (using TestClient)
"""

import asyncio
import json
import os
import sys
import tempfile
import time

import pytest
import pytest_asyncio

# ── Setup: point to a temp DB ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    """Use an isolated temp DB for each test."""
    db_path = str(tmp_path / "test.db")
    import core.memory as mem
    mem._DB_PATH = db_path
    yield db_path


@pytest.fixture(autouse=True)
def admin_token_env(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )


@pytest.fixture(autouse=True)
def event_loop_policy():
    """Use the default event loop policy."""
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


@pytest.fixture(autouse=True)
def reset_mcp_state(monkeypatch):
    monkeypatch.delenv("MCP_SERVERS_JSON", raising=False)
    monkeypatch.delenv("MCP_TOOL_TIMEOUT", raising=False)

    from tools import mcp

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(mcp.refresh_mcp_tools())
    finally:
        loop.close()


def _write_fake_mcp_server(tmp_path):
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(
        """
import json
import sys

TOOLS = [
    {
        "name": "echo_ticket",
        "description": "Echo back a test ticket payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "ticket": {"type": "string"},
            },
            "required": ["message"],
        },
    }
]


def read_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in {b"\\r\\n", b"\\n"}:
            break
        key, value = line.decode("ascii").split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers["content-length"])
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def send_message(payload):
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


while True:
    message = read_message()
    if message is None:
        break

    method = message.get("method")
    if method == "initialize":
        send_message(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-mcp", "version": "1.0.0"},
                },
            }
        )
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        send_message(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"tools": TOOLS},
            }
        )
    elif method == "tools/call":
        params = message.get("params", {})
        arguments = params.get("arguments", {})
        send_message(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Echoed: {arguments.get('message', '')}\\n"
                                f"Ticket: {arguments.get('ticket', 'INC0001234')}"
                            ),
                        }
                    ]
                },
            }
        )
    else:
        send_message(
            {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }
        )
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return script_path


# ── Memory tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_init_and_append():
    from core import memory
    await memory.init_db()

    await memory.append_message("conv-1", "alex-sre", "user", "Hello!")
    await memory.append_message("conv-1", "alex-sre", "assistant", "Hi there!")

    history = await memory.get_conversation_history("conv-1", "alex-sre")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_conversation_history_returns_most_recent_messages():
    from core import memory
    await memory.init_db()

    for idx in range(60):
        await memory.append_message("conv-recent", "alex-sre", "user", f"message-{idx}")

    history = await memory.get_conversation_history("conv-recent", "alex-sre", limit=5)
    assert [msg["content"] for msg in history] == [
        "message-55",
        "message-56",
        "message-57",
        "message-58",
        "message-59",
    ]


@pytest.mark.asyncio
async def test_audit_uses_updated_database_path(tmp_path):
    import core.memory as mem
    from core import audit

    db_path = str(tmp_path / "audit.db")
    mem.set_db_path(f"sqlite:///{db_path}")
    await mem.init_db()

    await audit.log_event("alex-sre", "message_received", details={"ok": True})
    events = await audit.get_events(limit=5)

    assert len(events) == 1
    assert events[0]["event_type"] == "message_received"


@pytest.mark.asyncio
async def test_episodic_memory():
    from core import memory
    await memory.init_db()

    await memory.store_episodic("alex-sre", "Resolved a Kubernetes pod crash", tags=["k8s", "incident"])

    results = await memory.search_episodic("alex-sre", "Kubernetes")
    assert len(results) >= 1
    assert "Kubernetes" in results[0]["summary"]


@pytest.mark.asyncio
async def test_entity_memory():
    from core import memory
    await memory.init_db()

    await memory.upsert_entity(
        agent_id="alex-sre",
        entity_name="oncall_schedule",
        entity_type="fact",
        facts={"current": "Alice", "next": "Bob"},
    )

    entity = await memory.get_entity("alex-sre", "oncall_schedule")
    assert entity is not None
    assert entity["facts"]["current"] == "Alice"

    # Upsert (merge)
    await memory.upsert_entity(
        agent_id="alex-sre",
        entity_name="oncall_schedule",
        entity_type="fact",
        facts={"timezone": "UTC"},
    )
    entity2 = await memory.get_entity("alex-sre", "oncall_schedule")
    assert "current" in entity2["facts"]
    assert "timezone" in entity2["facts"]


@pytest.mark.asyncio
async def test_agent_status():
    from core import memory
    await memory.init_db()

    status = await memory.get_agent_status("alex-sre")
    assert status == "active"  # default

    await memory.set_agent_status("alex-sre", "paused")
    status2 = await memory.get_agent_status("alex-sre")
    assert status2 == "paused"

    await memory.set_agent_status("alex-sre", "active")
    status3 = await memory.get_agent_status("alex-sre")
    assert status3 == "active"


# ── Tool tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_datetime_tool():
    from tools.datetime_tool import get_datetime
    result = await get_datetime("UTC")
    assert "UTC" in result
    assert "Date:" in result
    assert "Time:" in result


@pytest.mark.asyncio
async def test_datetime_tool_unknown_tz():
    from tools.datetime_tool import get_datetime
    result = await get_datetime("Invalid/Timezone")
    # Should fall back to UTC without crashing
    assert "Date:" in result


@pytest.mark.asyncio
async def test_shell_exec_safe():
    from tools.shell import shell_exec
    result = await shell_exec("echo hello world")
    assert "hello world" in result


@pytest.mark.asyncio
async def test_shell_exec_blocked():
    from tools.shell import shell_exec
    result = await shell_exec("rm -rf /")
    assert "blocked" in result.lower() or "❌" in result


@pytest.mark.asyncio
async def test_shell_exec_timeout():
    from tools.shell import shell_exec
    result = await shell_exec("sleep 60", timeout=1)
    assert "timed out" in result.lower() or "❌" in result


@pytest.mark.asyncio
async def test_memory_tool_store_recall():
    from core import memory
    from tools.memory_tool import memory_recall, memory_store
    await memory.init_db()

    store_result = await memory_store("test_key", "test_value_12345", agent_id="alex-sre")
    assert "✅" in store_result

    recall_result = await memory_recall("test_key", agent_id="alex-sre")
    assert "test_value_12345" in recall_result or "test_key" in recall_result


@pytest.mark.asyncio
async def test_jira_disabled_by_default(monkeypatch):
    from tools import jira

    monkeypatch.delenv("JIRA_MODE", raising=False)
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    result = await jira.jira_get_issue("ENG-123")
    assert "disabled" in result.lower()


@pytest.mark.asyncio
async def test_jira_mock_requires_explicit_mode(monkeypatch):
    from tools import jira

    monkeypatch.setenv("JIRA_MODE", "mock")
    result = await jira.jira_search("project = ENG")
    assert "[MOCK]" in result


@pytest.mark.asyncio
async def test_jira_live_mode_requires_full_config(monkeypatch):
    from tools import jira

    monkeypatch.setenv("JIRA_MODE", "live")
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    result = await jira.jira_get_issue("ENG-123")
    assert "misconfigured" in result.lower()
    assert "JIRA_EMAIL" in result
    assert "JIRA_API_TOKEN" in result


@pytest.mark.asyncio
async def test_jira_live_get_issue_uses_real_request(monkeypatch):
    from tools import jira

    monkeypatch.setenv("JIRA_MODE", "live")
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "agent@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "secret")

    async def fake_request(method: str, path: str, *, params=None, json_body=None):
        assert method == "GET"
        assert path == "/rest/api/3/issue/ENG-123"
        assert params is None
        assert json_body is None
        return {
            "key": "ENG-123",
            "fields": {
                "summary": "Investigate latency spike",
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "Jane Smith"},
                "reporter": {"displayName": "John Doe"},
                "description": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Customer-facing issue"}],
                        }
                    ],
                },
            },
        }

    monkeypatch.setattr(jira, "_jira_request", fake_request)
    result = await jira.jira_get_issue("ENG-123")
    assert "Issue: ENG-123" in result
    assert "Investigate latency spike" in result


@pytest.mark.asyncio
async def test_github_disabled_by_default(monkeypatch):
    from tools import github_issues

    monkeypatch.delenv("GITHUB_MODE", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)

    result = await github_issues.github_get_issue(123)
    assert "disabled" in result.lower()


@pytest.mark.asyncio
async def test_github_mock_requires_explicit_mode(monkeypatch):
    from tools import github_issues

    monkeypatch.setenv("GITHUB_MODE", "mock")
    result = await github_issues.github_search_issues("label:bug")
    assert "[MOCK]" in result


@pytest.mark.asyncio
async def test_github_live_mode_requires_full_config(monkeypatch):
    from tools import github_issues

    monkeypatch.setenv("GITHUB_MODE", "live")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    monkeypatch.delenv("GITHUB_REPO", raising=False)

    result = await github_issues.github_get_issue(123)
    assert "misconfigured" in result.lower()
    assert "GITHUB_REPO" in result


@pytest.mark.asyncio
async def test_github_live_get_issue_uses_real_request(monkeypatch):
    from tools import github_issues

    monkeypatch.setenv("GITHUB_MODE", "live")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    monkeypatch.setenv("GITHUB_REPO", "openai/project-talon")

    async def fake_request(method: str, path: str, *, params=None, json_body=None):
        assert method == "GET"
        assert path == "/repos/openai/project-talon/issues/123"
        assert params is None
        assert json_body is None
        return {
            "number": 123,
            "title": "Investigate flaky deployment",
            "state": "open",
            "user": {"login": "octocat"},
            "assignees": [{"login": "teammate"}],
            "labels": [{"name": "bug"}, {"name": "triage"}],
            "html_url": "https://github.com/openai/project-talon/issues/123",
            "body": "CI is failing intermittently on deploy.",
        }

    monkeypatch.setattr(github_issues, "_github_request", fake_request)
    result = await github_issues.github_get_issue(123)
    assert "openai/project-talon#123" in result
    assert "Investigate flaky deployment" in result


@pytest.mark.asyncio
async def test_servicenow_disabled_by_default(monkeypatch):
    from tools import servicenow

    monkeypatch.delenv("SERVICENOW_MODE", raising=False)
    monkeypatch.delenv("SERVICENOW_BASE_URL", raising=False)
    monkeypatch.delenv("SERVICENOW_USERNAME", raising=False)
    monkeypatch.delenv("SERVICENOW_PASSWORD", raising=False)

    result = await servicenow.servicenow_get_ticket("INC0012345")
    assert "disabled" in result.lower()


@pytest.mark.asyncio
async def test_servicenow_mock_requires_explicit_mode(monkeypatch):
    from tools import servicenow

    monkeypatch.setenv("SERVICENOW_MODE", "mock")
    result = await servicenow.servicenow_search_tickets("active=true")
    assert "[MOCK]" in result


@pytest.mark.asyncio
async def test_servicenow_live_mode_requires_full_config(monkeypatch):
    from tools import servicenow

    monkeypatch.setenv("SERVICENOW_MODE", "live")
    monkeypatch.setenv("SERVICENOW_BASE_URL", "https://example.service-now.com")
    monkeypatch.setenv("SERVICENOW_USERNAME", "agent")
    monkeypatch.delenv("SERVICENOW_PASSWORD", raising=False)

    result = await servicenow.servicenow_get_ticket("INC0012345")
    assert "misconfigured" in result.lower()
    assert "SERVICENOW_PASSWORD" in result


@pytest.mark.asyncio
async def test_servicenow_live_get_ticket_uses_real_request(monkeypatch):
    from tools import servicenow

    monkeypatch.setenv("SERVICENOW_MODE", "live")
    monkeypatch.setenv("SERVICENOW_BASE_URL", "https://example.service-now.com")
    monkeypatch.setenv("SERVICENOW_USERNAME", "agent")
    monkeypatch.setenv("SERVICENOW_PASSWORD", "secret")

    async def fake_request(method: str, path: str, *, params=None, json_body=None):
        assert method == "GET"
        assert path == "/api/now/table/incident"
        assert params["sysparm_query"] == "number=INC0012345"
        return {
            "result": [
                {
                    "number": "INC0012345",
                    "short_description": "VPN access issue",
                    "state": "2",
                    "priority": "2",
                    "urgency": "2",
                    "caller_id": {"display_value": "Jane Employee"},
                    "assigned_to": {"display_value": "Dana Helpdesk"},
                    "description": "Remote employee cannot connect to VPN.",
                }
            ]
        }

    monkeypatch.setattr(servicenow, "_servicenow_request", fake_request)
    result = await servicenow.servicenow_get_ticket("INC0012345")
    assert "INC0012345" in result
    assert "VPN access issue" in result


@pytest.mark.asyncio
async def test_mcp_disabled_by_default(monkeypatch):
    from tools import mcp

    monkeypatch.delenv("MCP_SERVERS_JSON", raising=False)
    status = await mcp.refresh_mcp_tools()

    assert status["status"] == "disabled"
    assert mcp.get_mcp_tool_definitions(["mcp:*"]) == []


@pytest.mark.asyncio
async def test_mcp_discovery_and_execution(monkeypatch, tmp_path):
    from tools import mcp
    from tools.registry import get_tool_definitions

    script_path = _write_fake_mcp_server(tmp_path)
    monkeypatch.setenv(
        "MCP_SERVERS_JSON",
        json.dumps(
            {
                "demo": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(script_path)],
                }
            }
        ),
    )

    status = await mcp.refresh_mcp_tools()
    assert status["status"] == "configured"
    assert status["discovered_tools"] == 1

    defs = get_tool_definitions(["mcp:*"])
    assert len(defs) == 1
    assert defs[0]["description"].startswith("[MCP:demo]")
    tool_name = defs[0]["name"]

    result = await mcp.execute_mcp_tool(
        tool_name,
        {"message": "hello from talon", "ticket": "INC0099999"},
    )
    assert "Echoed: hello from talon" in result
    assert "Ticket: INC0099999" in result
    assert "[MCP demo:echo_ticket]" in result


# ── Policy tests ──────────────────────────────────────────────────────────────

def test_policy_allows_normal():
    from core.policy import check_message
    allowed, reason = check_message("What's the status of the Kubernetes cluster?")
    assert allowed is True


def test_policy_blocks_hack():
    from core.policy import check_message
    allowed, reason = check_message("how to hack into the database")
    assert allowed is False
    assert reason != ""


def test_policy_shell_blocks_dangerous():
    from core.policy import check_shell_command
    allowed, reason = check_shell_command("rm -rf /")
    assert allowed is False


def test_policy_shell_allows_safe():
    from core.policy import check_shell_command
    allowed, reason = check_shell_command("ls -la /tmp")
    assert allowed is True


# ── Router tests ──────────────────────────────────────────────────────────────

def test_router_channel_routing():
    from channels.router import load_agents, route_message

    agents = {
        "alex-sre": {
            "id": "alex-sre",
            "name": "Alex",
            "role": "SRE",
            "channels": ["teams:#incidents"],
            "tools": [],
        },
        "dana-helpdesk": {
            "id": "dana-helpdesk",
            "name": "Dana",
            "role": "HelpDesk",
            "channels": ["teams:#it-support"],
            "tools": [],
        },
    }
    load_agents(agents)

    agent = route_message("pod is crashing", channel_name="#incidents")
    assert agent is not None
    assert agent["id"] == "alex-sre"


def test_router_mention_routing():
    from channels.router import load_agents, route_message, extract_mention

    agents = {
        "dana-helpdesk": {
            "id": "dana-helpdesk",
            "name": "Dana",
            "role": "HelpDesk",
            "channels": ["teams:#it-support"],
            "tools": [],
        },
    }
    load_agents(agents)

    text, mentioned = extract_mention("<at>Dana</at> I need a password reset")
    assert mentioned == "Dana"
    assert "password reset" in text

    agent = route_message(text, mentioned_agent=mentioned)
    assert agent is not None
    assert agent["id"] == "dana-helpdesk"


# ── Tool registry tests ───────────────────────────────────────────────────────

def test_registry_get_definitions():
    from tools.registry import get_tool_definitions
    defs = get_tool_definitions(["web_search", "datetime", "nonexistent_tool"])
    names = [d["name"] for d in defs]
    assert "web_search" in names
    assert "datetime" in names
    assert "nonexistent_tool" not in names


@pytest.mark.asyncio
async def test_registry_execute_datetime():
    from tools.registry import execute_tool
    result = await execute_tool("datetime", {"timezone_name": "UTC"})
    assert "Date:" in result


@pytest.mark.asyncio
async def test_registry_execute_unknown():
    from tools.registry import execute_tool
    result = await execute_tool("totally_fake_tool", {})
    assert "Unknown tool" in result


# ── FastAPI endpoint tests ────────────────────────────────────────────────────

@pytest.fixture
def test_client(tmp_path):
    """Create a test FastAPI client with a temp DB."""
    import asyncio
    import core.memory as mem
    db_path = str(tmp_path / "api_test.db")
    mem._DB_PATH = db_path

    # Initialise the DB synchronously before the client starts
    asyncio.get_event_loop().run_until_complete(mem.init_db())

    # Minimal agent setup
    from channels.router import load_agents
    load_agents({
        "alex-sre": {
            "id": "alex-sre",
            "name": "Alex",
            "role": "SRE",
            "emoji": "🔵",
            "color": "#3B82F6",
            "channels": ["teams:#incidents"],
            "tools": ["datetime"],
            "model": "claude-3-5-haiku-20241022",
            "system_prompt": "You are Alex, an SRE.",
        }
    })

    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as client:
        yield client


def admin_headers():
    return {"X-Admin-Token": "test-admin-token"}


def test_health_endpoint(test_client):
    resp = test_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["teams_integration"] == "not configured"
    assert data["github_integration"] == "disabled"
    assert data["servicenow_integration"] == "disabled"
    assert data["mcp_integration"]["status"] == "disabled"


def test_health_reports_partial_teams_config(test_client, monkeypatch):
    monkeypatch.setenv("TEAMS_APP_ID", "bot-app-id")
    monkeypatch.delenv("TEAMS_APP_PASSWORD", raising=False)
    monkeypatch.setenv("SKIP_SIGNATURE_VERIFICATION", "false")

    resp = test_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["teams_integration"] == "partially configured"


def test_health_reports_signature_bypass_mode(test_client, monkeypatch):
    monkeypatch.setenv("TEAMS_APP_ID", "bot-app-id")
    monkeypatch.setenv("TEAMS_APP_PASSWORD", "bot-secret")
    monkeypatch.setenv("SKIP_SIGNATURE_VERIFICATION", "true")

    resp = test_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["teams_integration"] == "configured (signature verification bypassed)"


@pytest.mark.asyncio
async def test_teams_auth_rejects_missing_app_id(monkeypatch):
    from channels import teams

    monkeypatch.delenv("TEAMS_APP_ID", raising=False)
    assert await teams._verify_bot_framework_auth("Bearer token") is False


@pytest.mark.asyncio
async def test_teams_auth_requires_bearer_prefix(monkeypatch):
    from channels import teams

    monkeypatch.setenv("TEAMS_APP_ID", "bot-app-id")
    assert await teams._verify_bot_framework_auth("token-only") is False


@pytest.mark.asyncio
async def test_teams_auth_uses_validated_token(monkeypatch):
    from channels import teams

    monkeypatch.setenv("TEAMS_APP_ID", "bot-app-id")

    async def fake_validate(token: str, app_id: str) -> bool:
        assert token == "valid-token"
        assert app_id == "bot-app-id"
        return True

    monkeypatch.setattr(teams, "_validate_bot_framework_token", fake_validate)
    assert await teams._verify_bot_framework_auth("Bearer valid-token") is True


def test_dashboard_employees(test_client):
    resp = test_client.get("/api/dashboard/employees", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "employees" in data
    assert len(data["employees"]) >= 1


def test_dashboard_metrics(test_client):
    resp = test_client.get("/api/dashboard/metrics", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert "conversations" in data


def test_employees_get(test_client):
    resp = test_client.get("/api/employees/alex-sre", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "alex-sre"
    assert data["name"] == "Alex"


def test_employees_get_not_found(test_client):
    resp = test_client.get("/api/employees/does-not-exist", headers=admin_headers())
    assert resp.status_code == 404


def test_admin_routes_require_token(test_client):
    resp = test_client.get("/api/dashboard/metrics")
    assert resp.status_code == 401

    resp = test_client.get("/api/dashboard/metrics", headers={"X-Admin-Token": "bad-token"})
    assert resp.status_code == 401


def test_pause_resume(test_client):
    # Pause
    resp = test_client.post("/api/employees/alex-sre/pause", headers=admin_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"

    # Resume
    resp = test_client.post("/api/employees/alex-sre/resume", headers=admin_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_audit_events(test_client):
    resp = test_client.get("/api/audit/events", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_hitl_memory_round_trip():
    from core import memory
    await memory.init_db()

    created = await memory.create_hitl_request(
        agent_id="alex-sre",
        task="Approve draining node prod-7",
        reason="Production impact requires operator confirmation",
        risk_level="high",
        requested_by="operator",
    )
    assert created["status"] == "pending"

    updated = await memory.update_hitl_request_status(created["id"], "approved", "Looks good")
    assert updated is not None
    assert updated["status"] == "approved"
    assert updated["resolution_note"] == "Looks good"


@pytest.mark.asyncio
async def test_scheduled_job_memory_round_trip():
    from core import memory
    await memory.init_db()

    job = await memory.create_scheduled_job(
        agent_id="alex-sre",
        name="Hourly digest",
        prompt="Summarize incident queue",
        interval_minutes=60,
        start_immediately=True,
    )
    assert job["status"] == "active"

    claimed = await memory.claim_due_scheduled_jobs()
    assert any(item["id"] == job["id"] for item in claimed)

    finished = await memory.finish_scheduled_job_run(
        job_id=job["id"],
        status="success",
        next_run_at=time.time() + 3600,
        response_preview="All clear",
        conversation_id="schedule-test",
    )
    assert finished is not None
    assert finished["last_result"] == "All clear"


@pytest.mark.asyncio
async def test_checkpoint_restore_round_trip():
    from core import memory
    await memory.init_db()

    await memory.append_message("conv-checkpoint", "alex-sre", "user", "before")
    await memory.store_episodic("alex-sre", "before-summary", tags=["before"])
    await memory.upsert_entity("alex-sre", "service", "fact", {"status": "green"})
    await memory.set_agent_status("alex-sre", "paused")
    await memory.create_hitl_request(
        agent_id="alex-sre",
        task="Approve change",
        reason="needs approval",
        risk_level="medium",
    )
    await memory.create_scheduled_job(
        agent_id="alex-sre",
        name="Digest",
        prompt="Summarize queue",
        interval_minutes=60,
    )

    checkpoint = await memory.create_agent_checkpoint(
        agent_id="alex-sre",
        label="before-mutation",
        summary="restore target",
        created_by="tester",
    )

    await memory.append_message("conv-checkpoint", "alex-sre", "assistant", "after")
    await memory.store_episodic("alex-sre", "after-summary", tags=["after"])
    await memory.set_agent_status("alex-sre", "active")
    jobs = await memory.list_scheduled_jobs(agent_id="alex-sre")
    await memory.set_scheduled_job_status(jobs[0]["id"], "paused")

    restore_result = await memory.restore_agent_checkpoint(
        checkpoint_id=checkpoint["id"],
        created_by="tester",
        create_safety_checkpoint=True,
    )
    assert restore_result["safety_checkpoint"] is not None

    history = await memory.get_conversation_history("conv-checkpoint", "alex-sre", limit=10)
    assert [item["content"] for item in history] == ["before"]

    episodic = await memory.get_recent_episodic("alex-sre", limit=10)
    assert [item["summary"] for item in episodic] == ["before-summary"]

    status = await memory.get_agent_status("alex-sre")
    assert status == "paused"

    restored_jobs = await memory.list_scheduled_jobs(agent_id="alex-sre")
    assert len(restored_jobs) == 1
    assert restored_jobs[0]["status"] == "active"


def test_hitl_endpoints(test_client):
    create_resp = test_client.post(
        "/api/hitl/requests",
        headers=admin_headers(),
        json={
            "agent_id": "alex-sre",
            "task": "Approve production change",
            "reason": "High-risk action requires review",
            "risk_level": "high",
            "requested_by": "qa",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["status"] == "pending"

    list_resp = test_client.get("/api/hitl/requests", headers=admin_headers())
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    approve_resp = test_client.post(
        f"/api/hitl/requests/{created['id']}/approve",
        headers=admin_headers(),
        json={"note": "Ship it"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    reject_resp = test_client.post(
        f"/api/hitl/requests/{created['id']}/reject",
        headers=admin_headers(),
        json={"note": "Too late"},
    )
    assert reject_resp.status_code == 409


def test_hitl_approve_still_works_if_agent_registry_changes(test_client):
    create_resp = test_client.post(
        "/api/hitl/requests",
        headers=admin_headers(),
        json={
            "agent_id": "alex-sre",
            "task": "Approve remediation",
            "reason": "Needs an operator",
            "risk_level": "medium",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    from channels.router import load_agents
    load_agents({})

    approve_resp = test_client.post(
        f"/api/hitl/requests/{created['id']}/approve",
        headers=admin_headers(),
        json={"note": "Proceed"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["agent_name"] == "alex-sre"


def test_policy_rules_endpoint_and_toggle(test_client):
    list_resp = test_client.get("/api/policy/rules", headers=admin_headers())
    assert list_resp.status_code == 200
    rules = list_resp.json()["rules"]
    assert len(rules) >= 1

    first_rule = rules[0]
    update_resp = test_client.put(
        f"/api/policy/rules/{first_rule['id']}",
        headers=admin_headers(),
        json={"enabled": False},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["rule"]["enabled"] is False


@pytest.mark.asyncio
async def test_policy_check_message_async_uses_opa(monkeypatch):
    from core import policy

    monkeypatch.setenv("POLICY_ENGINE", "opa")
    monkeypatch.setenv("OPA_BASE_URL", "http://opa:8181")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": {
                    "allowed": False,
                    "reason": "OPA blocked the message",
                    "matched_rules": ["msg-hacking"],
                }
            }

    class FakeClient:
        def __init__(self, timeout: int):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, json: dict):
            assert url == "http://opa:8181/v1/data/talon/decision"
            assert json["input"]["scope"] == "message"
            return FakeResponse()

    monkeypatch.setattr(policy.httpx, "AsyncClient", FakeClient)
    allowed, reason = await policy.check_message_async("how to hack")
    assert allowed is False
    assert reason == "OPA blocked the message"


def test_policy_status_endpoint(test_client):
    resp = test_client.get("/api/policy/status", headers=admin_headers())
    assert resp.status_code == 200
    assert "engine" in resp.json()
    assert "status" in resp.json()


def test_policy_sync_endpoint(test_client, monkeypatch):
    from core import policy

    async def fake_sync() -> dict:
        return {"synced": True, "engine": "opa", "rule_count": 3}

    monkeypatch.setattr(policy, "sync_opa_bundle", fake_sync)
    resp = test_client.post("/api/policy/sync", headers=admin_headers())
    assert resp.status_code == 200
    assert resp.json()["synced"] is True


def test_policy_rule_creation_endpoint(test_client):
    resp = test_client.post(
        "/api/policy/rules",
        headers=admin_headers(),
        json={
            "id": "tool-shell-curl",
            "name": "Block curl on shell tool input",
            "scope": "tool:shell_exec",
            "pattern": "curl",
            "action": "block",
            "description": "Blocks curl usage through shell tool calls",
            "enabled": True,
            "priority": 15,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["rule"]["id"] == "tool-shell-curl"


def test_schedule_endpoints(test_client):
    create_resp = test_client.post(
        "/api/schedules/jobs",
        headers=admin_headers(),
        json={
            "agent_id": "alex-sre",
            "name": "Hourly digest",
            "prompt": "Summarize the incidents channel",
            "interval_minutes": 60,
            "start_immediately": False,
        },
    )
    assert create_resp.status_code == 200
    job = create_resp.json()["job"]
    assert job["name"] == "Hourly digest"

    list_resp = test_client.get("/api/schedules/jobs", headers=admin_headers())
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    run_resp = test_client.post(
        f"/api/schedules/jobs/{job['id']}/run",
        headers=admin_headers(),
    )
    assert run_resp.status_code == 200

    pause_resp = test_client.post(
        f"/api/schedules/jobs/{job['id']}/pause",
        headers=admin_headers(),
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["job"]["status"] == "paused"

    resume_resp = test_client.post(
        f"/api/schedules/jobs/{job['id']}/resume",
        headers=admin_headers(),
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["job"]["status"] == "active"


def test_checkpoint_endpoints(test_client):
    pause_resp = test_client.post("/api/employees/alex-sre/pause", headers=admin_headers())
    assert pause_resp.status_code == 200

    create_resp = test_client.post(
        "/api/checkpoints",
        headers=admin_headers(),
        json={
            "agent_id": "alex-sre",
            "label": "before-restore",
            "summary": "checkpoint test",
            "created_by": "tester",
        },
    )
    assert create_resp.status_code == 200
    checkpoint = create_resp.json()["checkpoint"]

    resume_resp = test_client.post("/api/employees/alex-sre/resume", headers=admin_headers())
    assert resume_resp.status_code == 200

    restore_resp = test_client.post(
        f"/api/checkpoints/{checkpoint['id']}/restore",
        headers=admin_headers(),
        json={"created_by": "tester", "create_safety_checkpoint": True},
    )
    assert restore_resp.status_code == 200
    assert restore_resp.json()["safety_checkpoint"] is not None

    employee_resp = test_client.get("/api/employees/alex-sre", headers=admin_headers())
    assert employee_resp.status_code == 200
    assert employee_resp.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_kill_switch_state_round_trip():
    from core import memory
    await memory.init_db()

    state = await memory.set_kill_switch_state(True, "maintenance", "operator")
    assert state["active"] is True
    assert state["reason"] == "maintenance"

    cleared = await memory.set_kill_switch_state(False, "", "operator")
    assert cleared["active"] is False


def test_kill_switch_endpoint_blocks_direct_message(test_client):
    enable_resp = test_client.post(
        "/api/system/kill-switch",
        headers=admin_headers(),
        json={"active": True, "reason": "maintenance window", "updated_by": "tester"},
    )
    assert enable_resp.status_code == 200
    assert enable_resp.json()["kill_switch"]["active"] is True

    msg_resp = test_client.post(
        "/api/employees/alex-sre/message",
        headers=admin_headers(),
        json={"message": "hello", "user": "tester"},
    )
    assert msg_resp.status_code == 409
    assert "kill switch" in msg_resp.json()["detail"].lower()

    health_resp = test_client.get("/api/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["kill_switch"]["active"] is True

    disable_resp = test_client.post(
        "/api/system/kill-switch",
        headers=admin_headers(),
        json={"active": False, "reason": "", "updated_by": "tester"},
    )
    assert disable_resp.status_code == 200
    assert disable_resp.json()["kill_switch"]["active"] is False


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick smoke test without pytest
    print("Running smoke tests...")

    async def run_smoke():
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            import core.memory as mem
            mem._DB_PATH = os.path.join(tmpdir, "smoke.db")
            await mem.init_db()

            await mem.append_message("c1", "alex-sre", "user", "test")
            hist = await mem.get_conversation_history("c1", "alex-sre")
            assert hist[0]["content"] == "test"
            print("✅ Memory: OK")

            from tools.datetime_tool import get_datetime
            dt = await get_datetime("UTC")
            assert "Date:" in dt
            print("✅ DateTime tool: OK")

            from tools.shell import shell_exec
            out = await shell_exec("echo smoke test")
            assert "smoke test" in out
            print("✅ Shell tool: OK")

            from core.policy import check_message
            ok, _ = check_message("normal question")
            assert ok
            blocked, reason = check_message("how to hack")
            assert not blocked
            print("✅ Policy: OK")

        print("\n✅ All smoke tests passed!")

    asyncio.run(run_smoke())
