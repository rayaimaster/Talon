# Tool Layer README

This document explains how Talon's tool layer works, what tools exist today, and how to add more.

## What the Tool Layer Is

The tool layer is Talon's capability system.

It allows an agent to do more than generate text. A tool gives the agent a structured way to perform actions such as:

- searching the web
- running shell commands
- reading or writing long-term memory
- looking up or creating Jira issues
- looking up or creating GitHub Issues
- looking up or creating ServiceNow tickets
- discovering and calling MCP-backed tools

## Core Design

The main files in the tool layer are:

- `talon-backend/tools/registry.py`
  This is the tool contract and dispatch layer.
- `talon-backend/core/react_loop.py`
  This is where the LLM asks for tools, policy checks run, and results are fed back into the loop.
- `talon-backend/core/policy.py`
  This can block tool calls before execution.
- `talon-backend/config/agents.yaml`
  This controls which tools each agent is allowed to use.
- `talon-backend/tools/mcp.py`
  This discovers MCP tools from configured stdio servers and adapts them into Talon's registry.

## How Tool Execution Works

At runtime, the flow is:

1. An agent is loaded from `talon-backend/config/agents.yaml`.
2. The agent's allowed tool names are passed into `get_tool_definitions(...)` in `talon-backend/tools/registry.py`.
3. The LLM sees those tool definitions and may request a tool call.
4. `talon-backend/core/react_loop.py` receives the requested tool name and tool input.
5. Talon runs policy checks before execution.
6. `execute_tool(...)` in `talon-backend/tools/registry.py` dispatches the call to the real tool implementation.
7. The tool returns a string result.
8. The result is fed back into the ReAct loop so the model can continue reasoning.

## Tools Implemented Today

The current first-class tools are:

- `web_search`
  Implemented in `talon-backend/tools/web_search.py`
  Use case: find current information on the web.

- `shell_exec`
  Implemented in `talon-backend/tools/shell.py`
  Use case: diagnostics, system inspection, and bounded local command execution.

- `datetime`
  Implemented in `talon-backend/tools/datetime_tool.py`
  Use case: current time and timezone-aware date/time lookups.

- `memory_recall`
  Implemented in `talon-backend/tools/memory_tool.py`
  Use case: search long-term memory for related facts and prior context.

- `memory_store`
  Implemented in `talon-backend/tools/memory_tool.py`
  Use case: store facts in long-term memory for later use.

- `jira_get_issue`
- `jira_search`
- `jira_create_issue`
  Implemented in `talon-backend/tools/jira.py`
  Use case: read, search, and create Jira issues.

- `github_get_issue`
- `github_search_issues`
- `github_create_issue`
  Implemented in `talon-backend/tools/github_issues.py`
  Use case: read, search, and create GitHub Issues.

- `servicenow_get_ticket`
- `servicenow_search_tickets`
- `servicenow_create_ticket`
  Implemented in `talon-backend/tools/servicenow.py`
  Use case: read, search, and create ServiceNow tickets.

- `mcp__<server>__<tool>__<hash>` (discovered dynamically)
  Implemented in `talon-backend/tools/mcp.py`
  Use case: expose MCP server tools through Talon's native tool registry.

## Agent Access to Tools

Not every agent can use every tool.

The `tools:` list in `talon-backend/config/agents.yaml` controls which tools are exposed to each agent.

That means:

- adding a tool to the codebase is not enough
- the tool must also be listed for the relevant agent
- the agent prompt should usually be updated so the model knows the tool exists

For MCP-discovered tools, agent grants can use patterns instead of hard-coding the generated tool name:

- `mcp:*`
- `mcp:<server>:*`
- `mcp:<server>:<tool>`

## How to Add a New Tool

Use this pattern when adding a new tool:

1. Create a new tool file under `talon-backend/tools/`.

Example:

```python
async def servicenow_get_ticket(ticket_number: str) -> str:
    return "Ticket details..."
```

2. Register the tool definition in `_TOOL_DEFINITIONS` inside `talon-backend/tools/registry.py`.

That definition should include:

- the tool name
- a clear description
- a JSON input schema

3. Add dispatch logic to `execute_tool(...)` in `talon-backend/tools/registry.py`.

Example:

```python
elif tool_name == "servicenow_get_ticket":
    from tools.servicenow import servicenow_get_ticket
    return await servicenow_get_ticket(
        ticket_number=tool_input.get("ticket_number", "")
    )
```

4. Add the tool name to the right agent entries in `talon-backend/config/agents.yaml`.

5. If the tool is sensitive, add or update policy controls in `talon-backend/core/policy.py`.

Talon supports policy scopes like:

- `message`
- `shell`
- `tool:<tool_name>`

6. Add tests in `talon-backend/tests/test_agent.py`.

7. If the tool uses environment variables, update:

- `talon-backend/.env.example`
- `talon-backend/README.md`
- `LOCAL_RUN.md`
- `render.yaml`

## Recommended Tool Design Rules

A new Talon tool should ideally:

- do one clear job
- accept structured input through a simple schema
- return a readable string result
- fail with explicit error text instead of crashing
- support `disabled`, `mock`, and `live` modes if it depends on an external system
- be safe to audit and govern
- be testable without requiring live credentials

## Current External-Integration Pattern

Talon's external system tools currently follow an explicit mode contract:

- `disabled`
  The tool returns a clear disabled message.

- `mock`
  The tool returns deterministic demo/test data.

- `live`
  The tool calls the real external API and validates that required configuration exists.

This pattern is used by:

- `talon-backend/tools/jira.py`
- `talon-backend/tools/github_issues.py`
- `talon-backend/tools/servicenow.py`

## MCP in the Tool Layer

Talon now supports MCP as a dynamic tool source.

How it fits:

- `talon-backend/tools/mcp.py` reads `MCP_SERVERS_JSON`
- Talon starts each configured stdio MCP server during discovery
- Talon calls `tools/list` and adapts the returned schemas into Anthropic-format tool definitions
- discovered tools are exposed through `talon-backend/tools/registry.py`
- the ReAct loop uses those tools like any native Talon tool
- policy still applies because the final tool call still goes through the registry and policy layer

Current MCP scope:

- stdio transport only
- startup-time discovery
- tool execution through `tools/call`
- health/status reporting through `/api/health`

Example MCP config:

```env
MCP_SERVERS_JSON={"filesystem":{"transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"]}}
MCP_TOOL_TIMEOUT=30
```

## Where Policy Fits

Tool calls are not automatically trusted.

Before execution, Talon can evaluate the tool request through:

- the legacy in-process policy engine
- or OPA/Rego when `POLICY_ENGINE=opa`

This is especially important for powerful tools like:

- `shell_exec`
- future admin/infrastructure tools
- future write-capable enterprise integrations

## Good Candidates for Future Tools

Examples of tools that fit this architecture well:

- ServiceNow ticket tools
- Azure DevOps work item tools
- GitHub pull request tools
- Slack or Teams posting tools
- Confluence knowledge lookup tools
- internal status or incident API tools
- read-only reporting/database query tools

## Summary

The tool layer is the bridge between Talon's reasoning engine and the outside world.

The registry defines what the model can call, the policy layer governs whether it is allowed, and the tool implementation performs the real work. To add a new tool, implement it, register it, grant it to agents, protect it with policy as needed, test it, and document its configuration.
