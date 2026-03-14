# Project Talon Feature Gap Audit

This document compares the current codebase to the product/design story presented across the backend README and UI surface.

Status labels:

- `done`: implemented as real product behavior
- `partial`: present, but limited, mocked in places, or not productionized
- `missing`: not implemented as real backend-backed behavior

## Roadmap Progress

- [x] Wire `talon-app` to real backend APIs for metrics, employees, activity, audit, memory, and HITL.
- [x] Add persisted backend APIs for HITL request creation, approval, and rejection.
- [x] Replace local-only pause/resume behavior in `talon-app` with real API-backed operator controls.
- [x] Remove or relabel unsupported dashboard claims so prototype-only pages no longer masquerade as live platform behavior.
- [x] Add backend-managed policy rules and admin controls for real policy enforcement.
- [x] Add proactive scheduling and worker execution.
- [x] Add checkpointing and rollback primitives.
- [x] Add a backend-wide kill switch.
- [x] Implement full OPA/Rego policy evaluation.
- [ ] Replace SQLite before claiming multi-instance production readiness.

## Core Platform

| Feature | Status | Notes |
|---|---|---|
| Multi-provider LLM support | `done` | Real support exists for Anthropic, OpenAI-compatible/local, and Gemini in `talon-backend/core/llm_providers.py`. |
| ReAct loop orchestration | `done` | Implemented in `talon-backend/core/react_loop.py` with tool calls, memory replay, and audit logging. |
| Agent routing | `done` | Channel, mention, keyword, and fallback routing exist in `talon-backend/channels/router.py`. |
| Agent memory | `done` | Conversation history, episodic memory, entity memory, and agent status are implemented in `talon-backend/core/memory.py`. |
| Audit trail | `done` | Audit persistence and audit APIs exist in `talon-backend/core/audit.py` and `talon-backend/api/audit.py`. |
| Basic admin controls | `done` | Pause/resume and direct messaging are implemented in `talon-backend/api/employees.py`. |

## Web Chat Experience

| Feature | Status | Notes |
|---|---|---|
| Agent picker UI | `done` | Implemented in `talon-webchat/src/pages/AgentSelectPage.tsx`. |
| Real-time WebSocket chat | `done` | Implemented in `talon-webchat/src/hooks/useWebSocket.ts` and `talon-backend/channels/websocket.py`. |
| Typing indicators and streamed tool events | `done` | Implemented in the WebSocket protocol and rendered in `talon-webchat/src/components/MessageBubble.tsx`. |
| Markdown rendering and code blocks | `done` | Implemented in `talon-webchat/src/components/MessageBubble.tsx`. |
| Session persistence per agent | `done` | Implemented with `localStorage` in `talon-webchat/src/pages/ChatPage.tsx`. |
| Agent switch history reset | `done` | Fixed in `talon-webchat/src/pages/ChatPage.tsx`. |

## Integrations and Tools

| Feature | Status | Notes |
|---|---|---|
| Web search tool | `done` | Real DuckDuckGo-backed tool in `talon-backend/tools/web_search.py`. |
| Shell execution tool | `done` | Real sandboxed shell tool in `talon-backend/tools/shell.py`, with policy checks. |
| Date/time tool | `done` | Implemented in `talon-backend/tools/datetime_tool.py`. |
| Memory read/write tools | `done` | Implemented in `talon-backend/tools/memory_tool.py`. |
| Jira integration | `done` | Jira now uses an explicit mode contract in `talon-backend/tools/jira.py`: `disabled` by default, `mock` only when deliberately requested, and `live` with real config validation, clearer API failures, Render env wiring, and updated local/deploy docs. |
| GitHub Issues integration | `done` | GitHub Issues now has a first-class integration in `talon-backend/tools/github_issues.py` with explicit `disabled`/`mock`/`live` modes, real get/search/create issue support, Render env wiring, health reporting, tests, and updated local/deploy docs. |
| ServiceNow integration | `done` | ServiceNow now has a first-class integration in `talon-backend/tools/servicenow.py` with explicit `disabled`/`mock`/`live` modes, real get/search/create ticket support through the Table API, Render env wiring, health reporting, tests, and updated local/deploy docs. |
| MCP tool integration | `done` | Talon now supports stdio MCP servers through `talon-backend/tools/mcp.py`, with startup-time tool discovery, registry integration, health reporting, tests, and agent grants via `mcp:*`, `mcp:<server>:*`, or `mcp:<server>:<tool>`. |
| Microsoft Teams bot | `done` | Real webhook and reply logic exist in `talon-backend/channels/teams.py`, the Render/local env and smoke-test path are documented in `render.yaml`, `LOCAL_RUN.md`, and `talon-backend/README.md`, and incoming webhook auth now validates Bot Framework JWTs against Microsoft's OpenID metadata. |

## Deployment and Ops

| Feature | Status | Notes |
|---|---|---|
| Render deployment path for backend + webchat | `done` | Implemented in `render.yaml`. |
| Local run instructions | `done` | Implemented in `LOCAL_RUN.md`. |
| CI validation for backend and webchat build | `done` | Implemented in `.github/workflows/validate.yml`. |
| Restricted CORS | `done` | Implemented in `talon-backend/main.py` via `CORS_ORIGINS`. |
| Admin token protection | `done` | Implemented via `talon-backend/api/admin_auth.py` on employee, dashboard, and audit routes. |
| Production-ready persistence strategy | `partial` | SQLite on persistent disk is acceptable for single-instance v1, but not for HA or multi-instance scaling. |

## Dashboard / Control Plane

| Feature | Status | Notes |
|---|---|---|
| Dashboard overview | `done` | `talon-app` now reads backend metrics, employee inventory, activity, audit events, memory, and health via the live API in `talon-app/src/context/AppContext.tsx`. |
| Live observability data | `partial` | Health, activity, audit, provider, and queue data are now live-backed in `talon-app/src/pages/Observability.tsx`, but true time-series telemetry is still not exposed by the backend. |
| Real digital employee control plane | `partial` | Pause/resume controls are real and backend-backed in `talon-app/src/pages/DigitalEmployees.tsx` and `talon-app/src/pages/ControlPlane.tsx`, but advanced operating modes are still absent. |
| Real HITL approval workflow | `done` | Persisted HITL APIs now exist in `talon-backend/api/hitl.py`, with admin UI creation/approve/reject flows in `talon-app/src/pages/ControlPlane.tsx`. |
| Real policy enforcement | `done` | Policy rules remain admin-manageable in `talon-backend/api/policy.py`, and Talon now supports real OPA/Rego evaluation through `talon-backend/core/policy.py` when `POLICY_ENGINE=opa` and `OPA_BASE_URL` are configured. |
| Real proactive scheduling | `done` | Recurring interval jobs, run history, and worker execution are now implemented in `talon-backend/core/scheduler.py`, `talon-backend/api/schedules.py`, and `talon-app/src/pages/ControlPlane.tsx`. |
| Checkpointing and rollback | `done` | Per-agent checkpoints and rollback APIs are now implemented in `talon-backend/api/checkpoints.py` and surfaced in `talon-app/src/pages/ControlPlane.tsx`. |
| Global kill switch | `done` | A backend-wide kill switch now gates new work across direct messages, web chat, Teams, and scheduled jobs via `talon-backend/api/system_control.py` and `talon-app/src/pages/ControlPlane.tsx`. |

## Overall Assessment

### Fully delivered

- The backend agent platform
- The real-time webchat experience
- The Render deployment path for backend + webchat
- The live admin/control-plane foundation: HITL, policy management, scheduling, checkpoints, rollback, and kill switch

### Only partially delivered

- Ops/deployment maturity beyond single-instance SQLite
- Observability depth: health/activity/audit are live, but true time-series telemetry and richer usage/cost views are still absent
- Operator depth: pause/resume is real, but advanced operating modes beyond the current controls are still absent

### Main Remaining Gaps

1. Replace SQLite with a multi-instance-safe datastore before claiming HA or horizontal scaling.
2. Expand observability beyond the current health/activity/audit surfaces.
3. Add deeper operator modes and broader automated verification.

## Recommended Next Steps

1. Replace SQLite with a multi-instance-safe datastore before claiming HA or full production control-plane readiness.
2. Expand observability and operator modes beyond the current health/activity/audit and pause/resume controls.
