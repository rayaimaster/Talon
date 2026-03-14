# 🦅 Project Talon v2 — Digital Employee Platform

> **Enterprise Agentic Framework** · Real AI agents that live in Microsoft Teams and a beautiful web chat interface

Project Talon runs autonomous AI "digital employees" — each with a name, personality, and specialized role — that respond to messages in Microsoft Teams **and** a real-time web chat UI, use real tools, and remember past conversations.

---

## What's New in v2.0.0

- 🔀 **Multi-Provider LLM Support** — Use Anthropic Claude, OpenAI GPT, Google Gemini, LM Studio, Ollama, or any OpenAI-compatible local model, per agent
- 💬 **Real-time Web Chat** — Beautiful React frontend at `/workspace/talon-webchat/` with WebSocket streaming
- 📡 **WebSocket Streaming** — Watch agents think, use tools, and respond in real-time
- 🔌 **MCP Tool Support** — Discover and call stdio MCP server tools through Talon's native tool layer
- 🤖 **2 New Agents** — Casey (Communications) and Jordan (Finance)

---

## Architecture

```
Teams / WebSocket message
  → Agent Router
    → ReAct Loop (provider-agnostic)
      → LLM Provider (Anthropic | OpenAI | Local | Gemini)
        → Tools (web_search, shell_exec, datetime, memory, Jira, GitHub Issues, ServiceNow, MCP)
          → SQLite Memory
            → Reply (Teams | WebSocket | REST)
```

---

## LLM Provider Support

| Provider | Setting | Env Var | Notes |
|---|---|---|---|
| **Anthropic** (Claude) | `provider: anthropic` | `ANTHROPIC_API_KEY` | Default for all agents |
| **OpenAI** (GPT-4o, GPT-4o-mini) | `provider: openai` | `OPENAI_API_KEY` | Full tool calling |
| **LM Studio** | `provider: local` | `LOCAL_LLM_BASE_URL` | http://localhost:1234/v1 |
| **Ollama** | `provider: local` | `LOCAL_LLM_BASE_URL` | http://localhost:11434/v1 |
| **vLLM** | `provider: local` | `LOCAL_LLM_BASE_URL` | any OpenAI-compatible endpoint |
| **Google Gemini** | `provider: gemini` | `GEMINI_API_KEY` | Gemini 1.5 Flash/Pro |

### Per-Agent Provider Config (agents.yaml)

```yaml
agents:
  alex-sre:
    llm:
      provider: "anthropic"
      model: "claude-3-5-haiku-20241022"

  dana-helpdesk:
    llm:
      provider: "openai"
      model: "gpt-4o-mini"

  morgan-data:
    llm:
      provider: "local"
      model: "llama-3.2-3b-instruct"
      base_url: "http://localhost:1234/v1"
      api_key: "lm-studio"

  casey-comms:
    llm:
      provider: "gemini"
      model: "gemini-1.5-flash"
```

### Tool Calling for Local Models

Local models may not support tool calling natively. Talon automatically:
1. Tries OpenAI function-calling format first
2. Falls back to ReAct-style JSON prompting if the model returns plain text
3. Parses structured JSON tool calls from the plain text response

---

## Web Chat Interface

A real-time chat UI is available at `/workspace/talon-webchat/`.

**Features:**
- Agent picker page — select from all configured agents
- Real-time WebSocket connection with streaming events
- Typing indicators, tool call bubbles, tool result previews
- Markdown rendering with syntax highlighting
- Session persistence (localStorage)
- Auto-reconnect with exponential backoff
- Dark theme matching the platform aesthetic

**Build & deploy:**
```bash
cd talon-webchat
pnpm install
pnpm run build
# Deploy dist/ to your web server or CDN
```

**Connect to backend:** Set `VITE_API_URL` and `VITE_WS_URL` env vars before build.

---

## Quick Start

### 1. Install

```bash
cd talon-backend
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set at least one provider API key
```

### 3. Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Server starts at **http://localhost:8000**

- API docs: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws/chat/{agent_id}/{session_id}

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | If using Anthropic | Your Anthropic API key |
| `OPENAI_API_KEY` | If using OpenAI | Your OpenAI API key |
| `GEMINI_API_KEY` | If using Gemini | Your Google Gemini API key |
| `LOCAL_LLM_BASE_URL` | If using local | e.g. `http://localhost:1234/v1` |
| `LOCAL_LLM_API_KEY` | If using LM Studio | Any string (e.g. `lm-studio`) |
| `LOCAL_LLM_MODEL` | If using local | e.g. `llama-3.2-3b-instruct` |
| `TEAMS_APP_ID` | No | Azure Bot App ID |
| `TEAMS_APP_PASSWORD` | No | Azure Bot App Secret |
| `SKIP_SIGNATURE_VERIFICATION` | No | Set `true` only for local Teams webhook testing |
| `JIRA_MODE` | No | `disabled`, `mock`, or `live` |
| `JIRA_BASE_URL` | If `JIRA_MODE=live` | Jira base URL, e.g. `https://your-company.atlassian.net` |
| `JIRA_EMAIL` | If `JIRA_MODE=live` | Jira account email for API auth |
| `JIRA_API_TOKEN` | If `JIRA_MODE=live` | Jira API token |
| `GITHUB_MODE` | No | `disabled`, `mock`, or `live` |
| `GITHUB_TOKEN` | If `GITHUB_MODE=live` | GitHub token with Issues access |
| `GITHUB_REPO` | If `GITHUB_MODE=live` | Default repo in `owner/repo` format |
| `SERVICENOW_MODE` | No | `disabled`, `mock`, or `live` |
| `SERVICENOW_BASE_URL` | If `SERVICENOW_MODE=live` | ServiceNow instance URL |
| `SERVICENOW_USERNAME` | If `SERVICENOW_MODE=live` | ServiceNow username |
| `SERVICENOW_PASSWORD` | If `SERVICENOW_MODE=live` | ServiceNow password |
| `SERVICENOW_TABLE` | No | Default ServiceNow ticket table, e.g. `incident` |
| `MCP_SERVERS_JSON` | No | JSON config for one or more stdio MCP servers |
| `MCP_TOOL_TIMEOUT` | No | Default timeout in seconds for MCP discovery and tool calls |
| `POLICY_ENGINE` | No | `legacy` or `opa` |
| `OPA_BASE_URL` | If `POLICY_ENGINE=opa` | Base URL for the OPA server, e.g. `http://localhost:8181` |
| `OPA_FAIL_MODE` | No | `closed` to block on OPA errors, `open` to allow on OPA errors |
| `DATABASE_URL` | No | SQLite path (default: `sqlite:///talon.db`) |
| `CORS_ORIGINS` | No | Comma-separated allowed browser origins |
| `ADMIN_API_TOKEN` | No | Required for admin/control-plane APIs |
| `LOG_LEVEL` | No | Backend log verbosity |
| `HOST` | No | Bind host (default: `0.0.0.0`) |
| `PORT` | No | Bind port (default: `8000`) |

---

## Microsoft Teams Setup

### Local Teams testing

1. Set `TEAMS_APP_ID`, `TEAMS_APP_PASSWORD`, and `SKIP_SIGNATURE_VERIFICATION=true` in `.env`.
2. Run the backend locally and expose it with a public tunnel.
3. Point your Bot Framework messaging endpoint to `https://<public-url>/api/messages`.
4. Install the bot in Teams and verify greeting, routing, paused-agent replies, and kill-switch replies.

### Render deployment

The repo Blueprint now includes the Teams env contract for the backend service.

For deployed Teams support:

- set `TEAMS_APP_ID`
- set `TEAMS_APP_PASSWORD`
- keep `SKIP_SIGNATURE_VERIFICATION=false`
- point the Bot Framework messaging endpoint to `https://<render-backend>/api/messages`

Check `/api/health` after deploy. It should report `teams_integration: configured`.
Incoming webhook requests are validated against Microsoft's Bot Framework OpenID metadata unless you explicitly enable the local bypass mode.

For a full local step-by-step flow, see `../LOCAL_RUN.md`.

---

## Jira Setup

Jira is optional and now uses an explicit mode contract:

- `JIRA_MODE=disabled`: Jira tools return a clear disabled message
- `JIRA_MODE=mock`: Jira tools return demo-only fake data
- `JIRA_MODE=live`: Jira tools call the real Jira REST API

For real Jira, set:

- `JIRA_MODE=live`
- `JIRA_BASE_URL`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`

The health endpoint will then report `jira_integration: configured`.

---

## GitHub Issues Setup

GitHub Issues is optional and uses the same explicit mode contract:

- `GITHUB_MODE=disabled`: GitHub issue tools return a clear disabled message
- `GITHUB_MODE=mock`: GitHub issue tools return demo-only fake data
- `GITHUB_MODE=live`: GitHub issue tools call the real GitHub REST API

For real GitHub Issues, set:

- `GITHUB_MODE=live`
- `GITHUB_TOKEN`
- `GITHUB_REPO`

The health endpoint will then report `github_integration: configured`.

---

## ServiceNow Setup

ServiceNow is optional and uses the same explicit mode contract:

- `SERVICENOW_MODE=disabled`: ServiceNow tools return a clear disabled message
- `SERVICENOW_MODE=mock`: ServiceNow tools return demo-only fake data
- `SERVICENOW_MODE=live`: ServiceNow tools call the real ServiceNow Table API

For real ServiceNow, set:

- `SERVICENOW_MODE=live`
- `SERVICENOW_BASE_URL`
- `SERVICENOW_USERNAME`
- `SERVICENOW_PASSWORD`
- optionally `SERVICENOW_TABLE`

The health endpoint will then report `servicenow_integration: configured`.

---

## MCP Tool Integration

Talon now supports MCP as a first-class tool source.

Configured MCP servers are discovered at backend startup, and their tools are exposed through the same registry, ReAct loop, and policy path as native Talon tools.

Current scope:

- stdio MCP servers are supported
- discovered tools are surfaced as safe Talon tool names internally
- agent tool grants can use:
  - `mcp:*`
  - `mcp:<server>:*`
  - `mcp:<server>:<tool>`

Example configuration:

```env
MCP_SERVERS_JSON={"filesystem":{"transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"]}}
MCP_TOOL_TIMEOUT=30
```

After restart, `/api/health` will include an `mcp_integration` object with:

- overall status
- configured server count
- discovered tool count
- per-server discovery status

This means MCP tools can be governed by the same agent allowlists and policy controls as native tools.

---

## OPA / Rego Policy Engine

Talon now supports a real OPA/Rego policy boundary for message, shell, and tool-call checks.

- `POLICY_ENGINE=legacy`: use the in-process evaluator
- `POLICY_ENGINE=opa`: send policy decisions to OPA

For OPA mode, set:

- `POLICY_ENGINE=opa`
- `OPA_BASE_URL`
- `OPA_FAIL_MODE=closed` or `OPA_FAIL_MODE=open`

When OPA mode is enabled, Talon syncs the persisted policy rules into OPA data and evaluates requests through a Rego policy module. The health endpoint reports the current policy engine status, and admins can inspect or re-sync it via `/api/policy/status` and `/api/policy/sync`.

---

## API Reference

### WebSocket

```
ws://localhost:8000/ws/chat/{agent_id}/{session_id}
```

**Client → Server:**
```json
{"type": "message", "text": "Hello!", "user": "john.doe"}
{"type": "ping"}
```

**Server → Client:**
```json
{"type": "welcome",     "agent": "Alex", "role": "SRE Digital Employee"}
{"type": "typing",      "agent": "alex-sre"}
{"type": "tool_call",   "tool": "web_search", "input": "kubernetes pod crash"}
{"type": "tool_result", "tool": "web_search", "result": "..."}
{"type": "message",     "text": "Here's what I found...", "agent": "Alex"}
{"type": "error",       "text": "Something went wrong"}
{"type": "pong"}
```

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/agents` | List all agents (webchat) |
| `GET` | `/api/agents/{id}` | Single agent info |
| `GET` | `/api/chat/{id}/history/{session}` | Load chat history |
| `GET` | `/api/employees` | List agents (dashboard) |
| `POST` | `/api/employees/{id}/message` | Direct test message |
| `POST` | `/api/employees/{id}/pause` | Pause agent |
| `POST` | `/api/employees/{id}/resume` | Resume agent |
| `GET` | `/api/dashboard/metrics` | Platform metrics |
| `GET` | `/api/audit/events` | Audit trail |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/messages` | Teams Bot Framework webhook |

---

## Agents

| Agent | Emoji | Role | Default Provider |
|---|---|---|---|
| **Alex** | 🔵 | SRE Digital Employee | Anthropic |
| **Dana** | 🟢 | IT HelpDesk Digital Employee | Anthropic |
| **Morgan** | 🟣 | Data Analyst Digital Employee | Anthropic |
| **Casey** | 🟠 | Communications Digital Employee | Anthropic |
| **Jordan** | 🟡 | Finance Assistant Digital Employee | Anthropic |

---

## Project Structure

```
talon-backend/
├── main.py                    # FastAPI app + startup
├── requirements.txt
├── .env.example
├── config/
│   └── agents.yaml            # Agent personas + LLM provider config
├── core/
│   ├── llm_providers.py       # ★ NEW: Multi-provider LLM abstraction
│   ├── react_loop.py          # ReAct loop (provider-agnostic, ws_callback support)
│   ├── memory.py              # SQLite memory layer
│   ├── audit.py               # Audit trail
│   └── policy.py              # Safety checks
├── channels/
│   ├── websocket.py           # ★ NEW: WebSocket endpoint + /api/agents routes
│   ├── teams.py               # Bot Framework webhook
│   └── router.py              # Message routing logic
├── tools/
│   ├── registry.py            # Tool dispatch + definitions
│   ├── web_search.py          # DuckDuckGo search
│   ├── shell.py               # Sandboxed shell
│   ├── datetime_tool.py       # Date/time/timezone
│   ├── memory_tool.py         # Agent memory read/write
│   ├── jira.py                # Jira integration
│   ├── github_issues.py       # GitHub Issues integration
│   ├── servicenow.py          # ServiceNow integration
│   └── mcp.py                 # MCP stdio discovery + execution
├── api/
│   ├── dashboard.py           # Dashboard REST API
│   ├── employees.py           # Agent management
│   └── audit.py               # Audit endpoints
└── tests/
    └── test_agent.py          # Tests + smoke tests

talon-webchat/                 # ★ NEW: Web Chat Frontend
├── src/
│   ├── App.tsx                # Router
│   ├── config.ts              # API/WS URL config
│   ├── types.ts               # TypeScript interfaces
│   ├── hooks/
│   │   ├── useWebSocket.ts    # WS hook with auto-reconnect
│   │   └── useAgents.ts       # Agent list fetcher
│   ├── pages/
│   │   ├── AgentSelectPage.tsx # Agent picker grid
│   │   └── ChatPage.tsx        # Full chat interface
│   └── components/
│       ├── AgentCard.tsx       # Agent card (full + compact)
│       ├── MessageBubble.tsx   # Chat message rendering
│       ├── Sidebar.tsx         # Persistent agent sidebar
│       └── ConnectionBadge.tsx # WS connection indicator
└── dist/                      # Built output (deploy this)
```

---

## License

MIT — Use freely, deploy proudly.

---

*Built with ❤️ using FastAPI + Multi-provider LLMs + React + WebSockets*
