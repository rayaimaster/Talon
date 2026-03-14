# Run Project Talon Locally

This guide covers the supported local development path for:

- `talon-backend` as the FastAPI API, WebSocket service, scheduler, and Teams webhook
- `talon-webchat` as the browser chat UI
- `talon-app` as the live admin/control-plane UI

## Current Status

The app now supports all major product surfaces locally:

- backend agent platform
- web chat
- live admin/control plane
- optional Teams bot surface
- optional Jira integration
- optional GitHub Issues integration
- optional ServiceNow integration
- optional MCP server integration
- optional OPA/Rego policy evaluation

The main remaining platform limitation is persistence scale: local and current deployment flows still use SQLite unless you replace that layer.

## Prerequisites

- Python 3.11+
- Node.js 20+ with `corepack`
- Internet access for the first dependency install
- At least one LLM provider configured
- Optional for Teams testing: a Microsoft Bot registration plus a public tunnel URL

## 1. Configure and Start the Backend

```bash
cd /Users/ruiliu/Documents/Codex/EntAgentv2/code/talon-backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Edit `.env` and set these values at minimum:

```env
ANTHROPIC_API_KEY=your-key-here
ADMIN_API_TOKEN=local-dev-token
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174
DATABASE_URL=sqlite:///talon.db
LOG_LEVEL=INFO
SKIP_SIGNATURE_VERIFICATION=false
```

You can use another provider instead of Anthropic:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `LOCAL_LLM_BASE_URL` plus `LOCAL_LLM_API_KEY`

Jira is optional. The safest default is:

```env
JIRA_MODE=disabled
```

If you want demo-only fake Jira responses:

```env
JIRA_MODE=mock
```

If you want real Jira:

```env
JIRA_MODE=live
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-jira-api-token
```

GitHub Issues is also optional. The safest default is:

```env
GITHUB_MODE=disabled
```

If you want demo-only fake GitHub issue responses:

```env
GITHUB_MODE=mock
```

If you want real GitHub Issues:

```env
GITHUB_MODE=live
GITHUB_TOKEN=your-github-token
GITHUB_REPO=owner/repo
```

ServiceNow is also optional. The safest default is:

```env
SERVICENOW_MODE=disabled
```

If you want demo-only fake ServiceNow responses:

```env
SERVICENOW_MODE=mock
```

If you want real ServiceNow tickets:

```env
SERVICENOW_MODE=live
SERVICENOW_BASE_URL=https://your-instance.service-now.com
SERVICENOW_USERNAME=your-username
SERVICENOW_PASSWORD=your-password
SERVICENOW_TABLE=incident
```

MCP is also optional. To expose MCP tools to Talon, configure one or more stdio MCP servers:

```env
MCP_SERVERS_JSON={"filesystem":{"transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"]}}
MCP_TOOL_TIMEOUT=30
```

Agent tool grants can then use:

- `mcp:*` for all discovered MCP tools
- `mcp:filesystem:*` for all tools from one MCP server
- `mcp:filesystem:read_file` for one specific MCP tool

OPA/Rego policy evaluation is optional. To enable it, point Talon at a running OPA server:

```env
POLICY_ENGINE=opa
OPA_BASE_URL=http://localhost:8181
OPA_FAIL_MODE=closed
```

Start the backend:

```bash
cd /Users/ruiliu/Documents/Codex/EntAgentv2/code/talon-backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Expected local endpoints:

- Health: `http://localhost:8000/api/health`
- Docs: `http://localhost:8000/docs`
- WebSocket: `ws://localhost:8000/ws/chat/{agent_id}/{session_id}`
- Teams webhook: `http://localhost:8000/api/messages`

## 2. Start the Web Chat

Open a second terminal:

```bash
cd /Users/ruiliu/Documents/Codex/EntAgentv2/code/talon-webchat
corepack pnpm install --frozen-lockfile
VITE_API_URL=http://localhost:8000 corepack pnpm dev -- --host 0.0.0.0 --port 5173
```

Open:

- `http://localhost:5173`

On the setup screen, enter:

- `http://localhost:8000`

## 3. Start the Admin Console

Open a third terminal:

```bash
cd /Users/ruiliu/Documents/Codex/EntAgentv2/code/talon-app
corepack pnpm install --frozen-lockfile
VITE_API_URL=http://localhost:8000 \
VITE_ADMIN_API_TOKEN=local-dev-token \
corepack pnpm dev -- --host 0.0.0.0 --port 5174
```

Open:

- `http://localhost:5174`

You can either use the prefilled values or enter them manually:

- Backend API URL: `http://localhost:8000`
- `X-Admin-Token`: `local-dev-token`

## 4. Smoke Test the Main App Surfaces

### Public API checks

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/agents
```

Expected health highlights:

- `"status": "ok"`
- `"policy_engine": { ... }`
- `"teams_integration": "not configured"` unless you enabled Teams
- `"jira_integration": "disabled"` unless you enabled Jira
- `"github_integration": "disabled"` unless you enabled GitHub Issues
- `"servicenow_integration": "disabled"` unless you enabled ServiceNow
- `"mcp_integration": { "status": "disabled", ... }` unless you enabled MCP
- `"kill_switch": { "active": false, ... }`

Optional detailed checks:

```bash
curl http://localhost:8000/api/policy/status \
  -H "X-Admin-Token: local-dev-token"

curl http://localhost:8000/api/policy/rules \
  -H "X-Admin-Token: local-dev-token"
```

### Admin API checks

Routes under `/api/employees`, `/api/dashboard`, `/api/audit`, `/api/hitl`, `/api/policy`, `/api/schedules`, `/api/checkpoints`, and `/api/system/*` require `X-Admin-Token`.

```bash
curl http://localhost:8000/api/dashboard/metrics \
  -H "X-Admin-Token: local-dev-token"
```

```bash
curl http://localhost:8000/api/system/kill-switch \
  -H "X-Admin-Token: local-dev-token"
```

### Direct agent message check

```bash
curl http://localhost:8000/api/employees/alex-sre/message \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: local-dev-token" \
  -d '{"message":"What time is it in Tokyo?","user":"local-user"}'
```

### Browser checks

- In `talon-webchat`, select an agent and confirm a full request/response round-trip works.
- In `talon-app`, confirm metrics load, employees appear, and the control-plane pages show live backend data rather than placeholders.
- In `talon-app`, open the control plane and confirm the policy, HITL, schedules, checkpoints, and kill-switch sections all load without errors.

### Optional Jira smoke checks

If `JIRA_MODE=mock`, ask an agent that has Jira tools enabled to:

- fetch an issue like `ENG-123`
- search with a simple JQL query
- create a demo issue

If `JIRA_MODE=live`, verify the same flows against your real Jira project and confirm the returned browse URL is your real Jira host.

### Optional GitHub Issues smoke checks

If `GITHUB_MODE=mock`, ask an agent that has GitHub issue tools enabled to:

- fetch an issue like `#123`
- search issues with a query like `label:bug state:open`
- create a demo issue

If `GITHUB_MODE=live`, verify the same flows against your configured repository and confirm the returned issue URL is your real GitHub repo.

### Optional ServiceNow smoke checks

If `SERVICENOW_MODE=mock`, ask an agent that has ServiceNow tools enabled to:

- fetch a ticket like `INC0012345`
- search with a query like `active=true`
- create a demo ticket

If `SERVICENOW_MODE=live`, verify the same flows against your configured ServiceNow instance and confirm the returned ticket number and URL belong to your real instance.

### Optional MCP smoke checks

If `MCP_SERVERS_JSON` is set:

- restart the backend so MCP discovery runs again
- verify `/api/health` reports `"mcp_integration": { "status": "configured" | "degraded", ... }`
- grant an agent one of:
  - `mcp:*`
  - `mcp:<server>:*`
  - `mcp:<server>:<tool>`
- send that agent a prompt that should use the MCP-backed tool and confirm the response contains the MCP tool result

For example, if you configure the filesystem MCP server and grant `mcp:filesystem:*`, ask the agent to inspect a file inside the allowed directory and confirm the response uses the discovered MCP tool rather than a native Talon tool.

### Optional OPA/Rego smoke checks

If `POLICY_ENGINE=opa`, verify:

- `/api/health` reports `"policy_engine": { "engine": "opa", "status": "configured", ... }`
- `GET /api/policy/status` returns `engine=opa`
- `POST /api/policy/sync` succeeds with your admin token
- a blocked prompt like `how to hack` is denied through the normal chat/tool path

## 5. Optional: Test Microsoft Teams Locally

Use this only if you want to exercise the Teams webhook end to end.

### Backend env changes

Update `talon-backend/.env`:

```env
TEAMS_APP_ID=your-bot-app-id
TEAMS_APP_PASSWORD=your-bot-secret
SKIP_SIGNATURE_VERIFICATION=true
```

`SKIP_SIGNATURE_VERIFICATION=true` is for local webhook testing only. Keep it `false` in deployed environments.

Restart the backend after changing `.env`.

### Expose the webhook publicly

Expose `http://localhost:8000` through a tunnel such as `ngrok`, `cloudflared`, or Visual Studio dev tunnels, then use this public endpoint in your Bot registration:

- `https://<your-public-url>/api/messages`

### Configure the Bot Framework / Teams app

- In Azure Bot or Bot Framework, set the messaging endpoint to `https://<your-public-url>/api/messages`
- Make sure the App ID and secret match `TEAMS_APP_ID` and `TEAMS_APP_PASSWORD`
- Install the bot into the target Teams tenant, team, or personal scope

### Teams smoke test

Verify each of these behaviors:

- Add the bot to a chat or team and confirm it sends the greeting message
- Send a plain-language request and confirm Talon routes it to an agent
- Mention a specific agent and confirm it routes to that agent
- Pause an agent in `talon-app` and confirm Teams replies that the agent is paused
- Enable the global kill switch in `talon-app` and confirm Teams replies that new work is halted

The backend logs should also show the incoming Teams activity and any reply/send failures.

## 6. Production-Like Verification Commands

### Backend regression tests

```bash
cd /Users/ruiliu/Documents/Codex/EntAgentv2/code/talon-backend
source .venv/bin/activate
pytest tests/test_agent.py -q
```

This test suite is intended to be run with Python 3.11+.

### Web chat checks

```bash
cd /Users/ruiliu/Documents/Codex/EntAgentv2/code/talon-webchat
corepack pnpm exec tsc -b
VITE_API_URL=http://localhost:8000 corepack pnpm exec vite build
```

### Admin console checks

```bash
cd /Users/ruiliu/Documents/Codex/EntAgentv2/code/talon-app
corepack pnpm exec tsc -b
VITE_API_URL=http://localhost:8000 \
VITE_ADMIN_API_TOKEN=local-dev-token \
corepack pnpm exec vite build
```

### Suggested full local verification flow

1. Start the backend, webchat, and admin console.
2. Confirm `/api/health` returns `200` and reports the expected integration modes.
3. Send one successful chat request through `talon-webchat`.
4. Pause an agent in `talon-app` and confirm new work is blocked for that agent.
5. Create and resolve one HITL request in `talon-app`.
6. Create one scheduled job and confirm it appears in the schedule list.
7. Create one checkpoint and confirm it appears in the checkpoint list.
8. Activate the global kill switch and confirm direct messages are blocked.
9. If enabled, verify Jira, GitHub Issues, ServiceNow, MCP, OPA, and Teams using the optional checks above.

## 7. Render / Teams Deployment Notes

The Render Blueprint in the repo now includes the Teams env contract for `talon-backend`.

For deployed Teams support, make sure the backend service has:

- `TEAMS_APP_ID`
- `TEAMS_APP_PASSWORD`
- `SKIP_SIGNATURE_VERIFICATION=false`

Then point your Bot Framework messaging endpoint at:

- `https://<your-render-backend-host>/api/messages`

After deployment, verify:

- `https://<your-render-backend-host>/api/health` returns `"teams_integration": "configured"`
- the bot can receive and reply to a Teams message
- paused-agent and kill-switch replies behave the same way they do locally

If you are enabling Jira on Render, also set:

- `JIRA_MODE=live`
- `JIRA_BASE_URL`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`

After deployment, verify `/api/health` reports `"jira_integration": "configured"`.

If you are enabling GitHub Issues on Render, also set:

- `GITHUB_MODE=live`
- `GITHUB_TOKEN`
- `GITHUB_REPO`

After deployment, verify `/api/health` reports `"github_integration": "configured"`.

If you are enabling ServiceNow on Render, also set:

- `SERVICENOW_MODE=live`
- `SERVICENOW_BASE_URL`
- `SERVICENOW_USERNAME`
- `SERVICENOW_PASSWORD`
- optionally `SERVICENOW_TABLE`

After deployment, verify `/api/health` reports `"servicenow_integration": "configured"`.

If you are enabling MCP on Render, also set:

- `MCP_SERVERS_JSON`
- optionally `MCP_TOOL_TIMEOUT`

After deployment, verify `/api/health` reports `"mcp_integration": { "status": "configured" | "degraded", ... }`.

If you are enabling OPA on Render, also set:

- `POLICY_ENGINE=opa`
- `OPA_BASE_URL`
- `OPA_FAIL_MODE=closed`

After deployment, verify `/api/health` reports `"policy_engine": { "engine": "opa", "status": "configured", ... }`.

## 8. Common Local Issues

### Python version errors

The backend targets Python 3.11+. If `python3` points to 3.9 or 3.10, create the virtualenv with Python 3.11 explicitly.

### CORS errors in the browser

Make sure `CORS_ORIGINS` includes both local frontend origins you plan to use:

- `http://localhost:5173`
- `http://localhost:5174`

### Unauthorized admin route responses

Make sure your request includes:

```text
X-Admin-Token: <value of ADMIN_API_TOKEN>
```

### Teams health says `partially configured`

Set both `TEAMS_APP_ID` and `TEAMS_APP_PASSWORD`, then restart the backend.

### Teams health says `configured (signature verification bypassed)`

You are still in local-test mode. Set `SKIP_SIGNATURE_VERIFICATION=false` before using a deployed webhook.

### Jira health says `misconfigured (...)`

If `JIRA_MODE=live`, set all of:

- `JIRA_BASE_URL`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`

Or switch back to `JIRA_MODE=disabled` or `JIRA_MODE=mock`.

### GitHub health says `misconfigured (...)`

If `GITHUB_MODE=live`, set all of:

- `GITHUB_TOKEN`
- `GITHUB_REPO`

Or switch back to `GITHUB_MODE=disabled` or `GITHUB_MODE=mock`.

### ServiceNow health says `misconfigured (...)`

If `SERVICENOW_MODE=live`, set all of:

- `SERVICENOW_BASE_URL`
- `SERVICENOW_USERNAME`
- `SERVICENOW_PASSWORD`

You can also set `SERVICENOW_TABLE` if you do not want the default `incident` table.

Or switch back to `SERVICENOW_MODE=disabled` or `SERVICENOW_MODE=mock`.

### MCP health says `misconfigured` or `degraded`

Check:

- `MCP_SERVERS_JSON` is valid JSON
- each configured MCP server uses `transport=stdio`
- each server command exists on the backend host
- each server starts without waiting for interactive input
- you restarted the backend after changing MCP env vars

### OPA health says `misconfigured`

If `POLICY_ENGINE=opa`, set:

- `OPA_BASE_URL`
- optionally `OPA_FAIL_MODE=closed` or `OPA_FAIL_MODE=open`

If you do not want OPA locally, set `POLICY_ENGINE=legacy`.

### Web chat or admin console cannot connect

Check:

- backend is running on port `8000`
- the frontend is pointed to `http://localhost:8000`
- `/api/health` returns `200`
