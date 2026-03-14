# Render Production Readiness Plan for Project Talon

## Summary
Deploy `talon-backend` as a Render Python web service and `talon-webchat` as a Render static site using a repo-root `render.yaml` Blueprint. Do not deploy `talon-app` in v1 because it is still mock-data driven and not connected to backend APIs.

The current codebase is not production-ready yet. The main missing pieces are:
- No Render/IaC artifacts: missing `render.yaml`, service definitions, env-var contract, SPA rewrite, and disk strategy.
- No production safety on public/admin routes: `/api/employees/*`, `/api/dashboard/*`, and `/api/audit/*` are publicly callable.
- No production CORS policy: backend currently allows `*` with credentials.
- Core correctness gaps that will hurt production behavior:
  - audit DB path desync in `core/audit.py`
  - oldest-50 history bug in `core/memory.py`
  - chat state/history reset bug in `talon-webchat/src/pages/ChatPage.tsx`
- No real deployment verification layer: no runnable dependency/test setup for backend in the shipped package, and no frontend test coverage.
- No production observability or failure policy beyond basic logs and `/api/health`.
- SQLite is the only persistence layer; that is acceptable for single-instance v1 only, but not for horizontal scaling or zero-downtime deploys with a disk-backed service.

## Key Changes
### 1. Productionize the backend service
- Add repo-root `render.yaml` Blueprint with one `web` Python service for `talon-backend`.
- Configure backend service as:
  - `rootDir: talon-backend`
  - build command: `pip install -r requirements.txt`
  - start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
  - `healthCheckPath: /api/health`
  - plan: `starter`
- Attach a persistent disk and store SQLite at a fixed mount path, using:
  - `DATABASE_URL=sqlite:////opt/render/project/src/talon-data/talon.db`
- Keep the service single-instance. Do not enable horizontal scaling while SQLite is disk-backed.

### 2. Productionize the web chat
- Add a `static` service in `render.yaml` for `talon-webchat`.
- Configure static site as:
  - `rootDir: talon-webchat`
  - build command: `corepack enable && pnpm install --frozen-lockfile && pnpm build`
  - publish directory: `dist`
- Inject `VITE_API_URL` with the backend Render URL.
- Add a Render rewrite so all client-side routes resolve to `/index.html` for React Router.
- Fix chat page state so changing `agentId` resets `messages`, `isAgentTyping`, and `historyLoaded`, then reloads the correct conversation.

### 3. Close production blocking code gaps
- Fix `core/audit.py` so it always reads the live DB path from `core.memory` instead of importing `_DB_PATH` by value.
- Fix `core/memory.py` conversation history retrieval to return the newest `limit` rows, then re-order them oldest-to-newest before passing to the LLM/UI.
- Fix `talon-webchat/src/pages/ChatPage.tsx` route-change bug so agent switches do not retain stale transcript state.
- Add backend config for restricted CORS:
  - new env var: `CORS_ORIGINS`
  - parse as comma-separated origins
  - default to localhost-only in dev, explicit Render static-site origin in prod
- Add simple admin protection for non-chat operational endpoints:
  - new env var: `ADMIN_API_TOKEN`
  - require `X-Admin-Token` on `/api/employees/*`, `/api/dashboard/*`, and `/api/audit/*`
  - leave `/api/health`, `/api/agents*`, `/api/chat/*/history/*`, and WebSocket chat public for v1
- Exclude `talon-app` from the Blueprint and from deployment docs until it is API-backed.

### 4. Fill deployment and verification gaps
- Split runtime vs test dependencies:
  - keep runtime packages in `requirements.txt`
  - add a dev/test requirements file or extras including `pytest`, `pytest-asyncio`, and `httpx`
- Add a minimal CI/deploy check path:
  - backend tests for persistence, audit, history ordering, admin auth
  - frontend build check for `talon-webchat`
- Update deployment docs to match Render Blueprint flow, not local/systemd-first guidance.
- Define required secrets in Blueprint with dashboard-managed values:
  - `ANTHROPIC_API_KEY` or other provider keys
  - `ADMIN_API_TOKEN`
  - `LOG_LEVEL`
  - `CORS_ORIGINS`

## Public Interfaces / Config Changes
- Add repo-root `render.yaml` Blueprint for Render.
- Add env var `CORS_ORIGINS` to replace open CORS in production.
- Add env var `ADMIN_API_TOKEN` and require `X-Admin-Token` on admin/ops endpoints.
- Keep existing `DATABASE_URL`, but set it to the persistent disk path on Render.
- Keep existing `VITE_API_URL` contract for webchat; set it from the static site service config.

## Test Plan
- Backend regression tests:
  - `set_db_path()` updates the DB used by both memory and audit writes.
  - conversation history returns the most recent turns, not the oldest turns.
  - admin endpoints return `401/403` without `X-Admin-Token` and succeed with it.
  - `/api/health` returns 200 after startup on Render config.
- Frontend tests/checks:
  - webchat build succeeds with `VITE_API_URL`.
  - switching agents loads the correct session history and clears prior agent UI state.
  - direct navigation to `/chat/:agentId` works after adding the SPA rewrite.
- Deployment smoke tests:
  - backend responds on `/api/health`
  - `/api/agents` returns configured agents
  - browser can connect to `ws://.../ws/chat/{agent_id}/{session_id}`
  - one full chat round-trip succeeds
  - restart/redeploy preserves SQLite data on disk

## Assumptions and Defaults
- Chosen deployment target is Render Blueprint, not direct manual service creation, because this app has two deployable services and needs reproducible config.
- Teams integration is deferred; first production release is backend + web chat only.
- `talon-app` is intentionally excluded because it currently serves simulated state from [`AppContext.tsx`](/tmp/talon-review/talon-app/src/context/AppContext.tsx#L41), not live backend data.
- SQLite remains the v1 datastore. This is acceptable only for a single Render web service with a persistent disk; if HA, multi-instance scale, or safer deploys are required later, move to managed Postgres before scaling.
- Render references used for this plan:
  - [Deploy a FastAPI App](https://render.com/docs/deploy-fastapi)
  - [Static Sites](https://render.com/docs/static-sites)
  - [Blueprint YAML Reference](https://render.com/docs/blueprint-spec)
  - [Persistent Disks](https://render.com/docs/disks)
  - [Health Checks](https://render.com/docs/health-checks)
