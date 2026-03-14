"""
Project Talon — Digital Employee Platform
FastAPI application entry point.

v2.0.0 additions:
  - Multi-provider LLM support (Anthropic, OpenAI, Local, Gemini)
  - Real-time WebSocket chat interface
  - New REST endpoints: GET /api/agents, GET /api/agents/{id}, GET /api/chat/.../history/...
"""

import logging
import os
from contextlib import asynccontextmanager

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# ── Load environment ──────────────────────────────────────────────────────────
load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Import core modules (after env is loaded) ─────────────────────────────────
from core import memory, policy
from core.scheduler import get_scheduler_service
from core.audit import log_event
from tools.github_issues import get_github_status
from tools.jira import get_jira_status
from tools.mcp import get_mcp_status, refresh_mcp_tools
from tools.servicenow import get_servicenow_status

# ── Import routers ────────────────────────────────────────────────────────────
from channels.teams import router as teams_router
from channels.websocket import router as ws_router
from api.dashboard import router as dashboard_router
from api.employees import router as employees_router
from api.audit import router as audit_router
from api.hitl import router as hitl_router
from api.policy import router as policy_router
from api.schedules import router as schedules_router
from api.checkpoints import router as checkpoints_router
from api.system_control import router as system_control_router
from channels.router import load_agents


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic using the modern lifespan context manager."""
    # ── STARTUP ───────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("  Project Talon — Digital Employee Platform v2.0.0")
    logger.info("=" * 60)

    # Init database
    db_url = os.environ.get("DATABASE_URL", "sqlite:///talon.db")
    memory.set_db_path(db_url)
    await memory.init_db()
    await policy.ensure_policy_rules()
    await policy.refresh_policy_cache()
    await refresh_mcp_tools()
    logger.info("Database ready: %s", db_url)

    # Load agent configs
    config_path = os.path.join(os.path.dirname(__file__), "config", "agents.yaml")
    agents = _load_agents(config_path)
    load_agents(agents)
    logger.info("Loaded %d agents: %s", len(agents), list(agents.keys()))

    # Log LLM provider config for each agent
    for agent_id, config in agents.items():
        llm = config.get("llm", {})
        provider = llm.get("provider", "anthropic")
        model = llm.get("model") or config.get("model", "claude-3-5-haiku-20241022")
        logger.info(
            "  Agent %-20s provider=%-10s model=%s",
            agent_id, provider, model,
        )

    # Check provider keys — warn but don't fail (backend starts without keys)
    _check_provider_keys(agents)

    policy_status = policy.get_policy_status()
    if policy_status["engine"] == "opa" and policy_status["status"] == "configured":
        logger.info("Policy engine: OPA/Rego configured ✓")
    elif policy_status["engine"] == "opa":
        logger.warning("Policy engine: %s", policy_status["detail"])
    else:
        logger.info("Policy engine: legacy in-process evaluator")

    # Teams config
    teams_status = _get_teams_integration_status()
    if teams_status == "configured":
        logger.info("Microsoft Teams: configured ✓")
    elif teams_status == "configured (signature verification bypassed)":
        logger.warning(
            "Microsoft Teams: configured, but SKIP_SIGNATURE_VERIFICATION=true. "
            "Use this mode for local testing only."
        )
    elif teams_status == "partially configured":
        logger.warning(
            "Microsoft Teams: partially configured. Set both TEAMS_APP_ID and "
            "TEAMS_APP_PASSWORD for a full deployment."
        )
    else:
        logger.info(
            "Microsoft Teams: not configured (local testing mode). "
            "Set TEAMS_APP_ID + TEAMS_APP_PASSWORD to enable."
        )

    jira_status = get_jira_status()
    if jira_status == "configured":
        logger.info("Jira integration: configured ✓")
    elif jira_status == "mock":
        logger.warning(
            "Jira integration: explicit mock mode enabled. "
            "Use this for demos/testing only."
        )
    elif jira_status.startswith("misconfigured"):
        logger.warning("Jira integration: %s", jira_status)
    else:
        logger.info(
            "Jira integration: disabled. Set JIRA_MODE=live with JIRA_BASE_URL, "
            "JIRA_EMAIL, and JIRA_API_TOKEN to enable."
        )

    github_status = get_github_status()
    if github_status == "configured":
        logger.info("GitHub Issues integration: configured ✓")
    elif github_status == "mock":
        logger.warning(
            "GitHub Issues integration: explicit mock mode enabled. "
            "Use this for demos/testing only."
        )
    elif github_status.startswith("misconfigured"):
        logger.warning("GitHub Issues integration: %s", github_status)
    else:
        logger.info(
            "GitHub Issues integration: disabled. Set GITHUB_MODE=live with "
            "GITHUB_TOKEN and GITHUB_REPO to enable."
        )

    servicenow_status = get_servicenow_status()
    if servicenow_status == "configured":
        logger.info("ServiceNow integration: configured ✓")
    elif servicenow_status == "mock":
        logger.warning(
            "ServiceNow integration: explicit mock mode enabled. "
            "Use this for demos/testing only."
        )
    elif servicenow_status.startswith("misconfigured"):
        logger.warning("ServiceNow integration: %s", servicenow_status)
    else:
        logger.info(
            "ServiceNow integration: disabled. Set SERVICENOW_MODE=live with "
            "SERVICENOW_BASE_URL, SERVICENOW_USERNAME, and SERVICENOW_PASSWORD to enable."
        )

    mcp_status = get_mcp_status()
    if mcp_status["status"] == "configured":
        logger.info("MCP integration: configured ✓ (%d tool(s))", mcp_status["discovered_tools"])
    elif mcp_status["status"] == "degraded":
        logger.warning("MCP integration: degraded. %s", mcp_status["detail"])
    elif mcp_status["status"] == "misconfigured":
        logger.warning("MCP integration: %s", mcp_status["detail"])
    else:
        logger.info("MCP integration: disabled. Set MCP_SERVERS_JSON to enable MCP servers.")

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    logger.info("=" * 60)
    logger.info("  Server running at http://%s:%d", host, port)
    logger.info("  API docs:         http://localhost:%d/docs", port)
    logger.info("  WebSocket chat:   ws://localhost:%d/ws/chat/{agent_id}/{session_id}", port)
    logger.info("  Web Chat UI:      serve /workspace/talon-webchat/dist/")
    logger.info("=" * 60)

    scheduler = get_scheduler_service()
    await scheduler.start()

    yield  # ── Application runs here ──────────────────────────────────────────

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    await scheduler.stop()
    logger.info("Project Talon shutting down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Project Talon — Digital Employee Platform",
    description=(
        "Enterprise Agentic Framework: AI agents that live in Microsoft Teams "
        "and help your team with SRE, IT support, data analysis, and more.\n\n"
        "**v2.0.0**: Multi-provider LLM support (Anthropic, OpenAI, Local, Gemini) "
        "and real-time WebSocket chat interface."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

cors_origins = _get_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──────────────────────────────────────────────────────────
app.include_router(teams_router)
app.include_router(ws_router)          # WebSocket + /api/agents endpoints
app.include_router(dashboard_router)
app.include_router(employees_router)
app.include_router(audit_router)
app.include_router(hitl_router)
app.include_router(policy_router)
app.include_router(schedules_router)
app.include_router(checkpoints_router)
app.include_router(system_control_router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
async def health_check() -> dict:
    """Health check endpoint for load balancers and monitoring."""
    from channels.websocket import manager as ws_manager

    providers_configured = {
        "anthropic": bool(
            os.environ.get("ANTHROPIC_API_KEY", "").strip()
            and not os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-...")
        ),
        "openai": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "gemini": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
        "local": bool(os.environ.get("LOCAL_LLM_BASE_URL", "").strip()),
    }

    return {
        "status": "ok",
        "service": "Project Talon",
        "version": "2.0.0",
        "providers": providers_configured,
        "kill_switch": await memory.get_kill_switch_state(),
        "policy_engine": policy.get_policy_status(),
        "teams_integration": _get_teams_integration_status(),
        "jira_integration": get_jira_status(),
        "github_integration": get_github_status(),
        "servicenow_integration": get_servicenow_status(),
        "mcp_integration": get_mcp_status(),
        "websocket_connections": ws_manager.active_connections,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_agents(config_path: str) -> dict[str, dict]:
    """Load and validate the agents.yaml config."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("agents.yaml not found at %s", config_path)
        return {}
    except yaml.YAMLError as exc:
        logger.error("Failed to parse agents.yaml: %s", exc)
        return {}

    agents_raw = raw.get("agents", {})
    agents: dict[str, dict] = {}
    for agent_id, config in agents_raw.items():
        if not isinstance(config, dict):
            continue
        # Inject the ID into the config for convenience
        config["id"] = agent_id
        agents[agent_id] = config

    return agents


def _get_teams_integration_status() -> str:
    app_id_set = bool(os.environ.get("TEAMS_APP_ID", "").strip())
    password_set = bool(os.environ.get("TEAMS_APP_PASSWORD", "").strip())
    skip_signature = os.environ.get("SKIP_SIGNATURE_VERIFICATION", "").lower() in ("true", "1", "yes")

    if app_id_set and password_set:
        if skip_signature:
            return "configured (signature verification bypassed)"
        return "configured"
    if app_id_set or password_set:
        return "partially configured"
    return "not configured"


def _get_cors_origins() -> list[str]:
    """Return the explicit set of CORS origins allowed to access the API."""
    configured = os.environ.get("CORS_ORIGINS", "").strip()
    if configured:
        origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
        if origins:
            return origins

    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def _check_provider_keys(agents: dict) -> None:
    """Warn about missing API keys for configured providers."""
    providers_needed = set()
    for config in agents.values():
        llm = config.get("llm", {})
        provider = llm.get("provider", "anthropic")
        providers_needed.add(provider)

    if "anthropic" in providers_needed:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or key.startswith("sk-ant-..."):
            logger.warning(
                "⚠️  ANTHROPIC_API_KEY not set. Agents using Anthropic will fail."
            )
        else:
            logger.info("Anthropic API key: configured ✓")

    if "openai" in providers_needed:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            logger.warning(
                "⚠️  OPENAI_API_KEY not set. Agents using OpenAI will fail."
            )
        else:
            logger.info("OpenAI API key: configured ✓")

    if "gemini" in providers_needed:
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            logger.warning(
                "⚠️  GEMINI_API_KEY not set. Agents using Gemini will fail."
            )
        else:
            logger.info("Gemini API key: configured ✓")

    if "local" in providers_needed:
        base_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
        logger.info("Local LLM endpoint: %s", base_url)


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "false").lower() in ("true", "1")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level.lower(),
    )
