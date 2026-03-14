"""
Tool registry for Project Talon.

Maintains the mapping from tool name → (function, Anthropic tool definition).
The ReAct loop queries this to know which tools to expose to Claude and
how to execute them.
"""

import logging
from typing import Any, Callable, Coroutine

from tools.mcp import execute_mcp_tool, get_mcp_tool_definitions, list_mcp_tools

logger = logging.getLogger(__name__)

# ── Tool definitions (Anthropic format) ──────────────────────────────────────
# Each entry: { "name": ..., "description": ..., "input_schema": {...} }

_TOOL_DEFINITIONS: dict[str, dict] = {
    "web_search": {
        "name": "web_search",
        "description": (
            "Search the web using DuckDuckGo. Use this to find current information, "
            "documentation, news, or anything you don't know from memory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 10).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    "shell_exec": {
        "name": "shell_exec",
        "description": (
            "Execute a shell command on the server. "
            "Use for system diagnostics, file inspection, git operations, etc. "
            "Commands are sandboxed and time-limited. "
            "Dangerous commands (rm -rf /, etc.) are blocked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 30, max 120).",
                    "default": 30,
                },
            },
            "required": ["command"],
        },
    },
    "datetime": {
        "name": "datetime",
        "description": (
            "Get the current date and time, optionally in a specific timezone. "
            "Use IANA timezone names like 'UTC', 'US/Eastern', 'Europe/London', 'Asia/Tokyo'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "timezone_name": {
                    "type": "string",
                    "description": "IANA timezone name (default: 'UTC').",
                    "default": "UTC",
                },
            },
            "required": [],
        },
    },
    "memory_recall": {
        "name": "memory_recall",
        "description": (
            "Search your long-term memory for information related to a topic. "
            "Use this to recall past conversations, stored facts, and episodic memories."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in memory.",
                },
            },
            "required": ["query"],
        },
    },
    "memory_store": {
        "name": "memory_store",
        "description": (
            "Store a fact or piece of information in your long-term memory "
            "for future recall. Use a descriptive key."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "A descriptive key for the memory (e.g. 'oncall_rotation_q1').",
                },
                "value": {
                    "type": "string",
                    "description": "The information to store.",
                },
            },
            "required": ["key", "value"],
        },
    },
    "jira_get_issue": {
        "name": "jira_get_issue",
        "description": "Fetch a Jira issue by its key (e.g. 'ENG-123').",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "The Jira issue key, e.g. 'ENG-123'.",
                },
            },
            "required": ["issue_key"],
        },
    },
    "jira_search": {
        "name": "jira_search",
        "description": "Search Jira issues using JQL (Jira Query Language).",
        "input_schema": {
            "type": "object",
            "properties": {
                "jql": {
                    "type": "string",
                    "description": "JQL query string, e.g. 'project = ENG AND status = Open'.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default 10).",
                    "default": 10,
                },
            },
            "required": ["jql"],
        },
    },
    "jira_create_issue": {
        "name": "jira_create_issue",
        "description": "Create a new Jira issue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": "Jira project key, e.g. 'ENG'.",
                },
                "summary": {
                    "type": "string",
                    "description": "Issue title/summary.",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the issue.",
                    "default": "",
                },
                "issue_type": {
                    "type": "string",
                    "description": "Issue type: Task, Bug, Story, Epic (default: Task).",
                    "default": "Task",
                },
                "priority": {
                    "type": "string",
                    "description": "Priority: Highest, High, Medium, Low, Lowest (default: Medium).",
                    "default": "Medium",
                },
            },
            "required": ["project_key", "summary"],
        },
    },
    "github_get_issue": {
        "name": "github_get_issue",
        "description": "Fetch a GitHub issue by number from the configured repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_number": {
                    "type": "integer",
                    "description": "The GitHub issue number, e.g. 123.",
                },
                "repo": {
                    "type": "string",
                    "description": "Optional repo override in owner/repo format.",
                    "default": "",
                },
            },
            "required": ["issue_number"],
        },
    },
    "github_search_issues": {
        "name": "github_search_issues",
        "description": "Search GitHub issues using GitHub issue search syntax.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. 'label:bug state:open'.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default 10).",
                    "default": 10,
                },
                "repo": {
                    "type": "string",
                    "description": "Optional repo override in owner/repo format.",
                    "default": "",
                },
            },
            "required": ["query"],
        },
    },
    "github_create_issue": {
        "name": "github_create_issue",
        "description": "Create a new GitHub issue in the configured repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Issue title.",
                },
                "body": {
                    "type": "string",
                    "description": "Detailed issue body.",
                    "default": "",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional labels to apply.",
                    "default": [],
                },
                "repo": {
                    "type": "string",
                    "description": "Optional repo override in owner/repo format.",
                    "default": "",
                },
            },
            "required": ["title"],
        },
    },
    "servicenow_get_ticket": {
        "name": "servicenow_get_ticket",
        "description": "Fetch a ServiceNow ticket by number from the configured table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_number": {
                    "type": "string",
                    "description": "ServiceNow ticket number, e.g. 'INC0012345'.",
                },
                "table": {
                    "type": "string",
                    "description": "Optional ServiceNow table override, e.g. 'incident'.",
                    "default": "",
                },
            },
            "required": ["ticket_number"],
        },
    },
    "servicenow_search_tickets": {
        "name": "servicenow_search_tickets",
        "description": "Search ServiceNow tickets using a sysparm_query string.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "ServiceNow sysparm_query, e.g. 'active=true^priority=1'.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default 10).",
                    "default": 10,
                },
                "table": {
                    "type": "string",
                    "description": "Optional ServiceNow table override, e.g. 'incident'.",
                    "default": "",
                },
            },
            "required": ["query"],
        },
    },
    "servicenow_create_ticket": {
        "name": "servicenow_create_ticket",
        "description": "Create a new ServiceNow ticket in the configured table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "short_description": {
                    "type": "string",
                    "description": "Short description / title of the ticket.",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed ticket description.",
                    "default": "",
                },
                "urgency": {
                    "type": "string",
                    "description": "Urgency value, default '3'.",
                    "default": "3",
                },
                "impact": {
                    "type": "string",
                    "description": "Impact value, default '3'.",
                    "default": "3",
                },
                "caller_id": {
                    "type": "string",
                    "description": "Optional caller identifier.",
                    "default": "",
                },
                "table": {
                    "type": "string",
                    "description": "Optional ServiceNow table override, e.g. 'incident'.",
                    "default": "",
                },
            },
            "required": ["short_description"],
        },
    },
}


async def execute_tool(tool_name: str, tool_input: dict, agent_id: str = "") -> str:
    """
    Dispatch a tool call by name.

    Returns the tool's string output, or an error message.
    """
    # Import here to avoid circular imports and to keep startup fast
    if tool_name == "web_search":
        from tools.web_search import web_search
        return await web_search(
            query=tool_input.get("query", ""),
            num_results=min(int(tool_input.get("num_results", 5)), 10),
        )

    elif tool_name == "shell_exec":
        from tools.shell import shell_exec
        return await shell_exec(
            command=tool_input.get("command", ""),
            timeout=min(int(tool_input.get("timeout", 30)), 120),
        )

    elif tool_name == "datetime":
        from tools.datetime_tool import get_datetime
        return await get_datetime(
            timezone_name=tool_input.get("timezone_name", "UTC"),
        )

    elif tool_name == "memory_recall":
        from tools.memory_tool import memory_recall
        return await memory_recall(
            query=tool_input.get("query", ""),
            agent_id=agent_id,
        )

    elif tool_name == "memory_store":
        from tools.memory_tool import memory_store
        return await memory_store(
            key=tool_input.get("key", "unknown"),
            value=tool_input.get("value", ""),
            agent_id=agent_id,
        )

    elif tool_name == "jira_get_issue":
        from tools.jira import jira_get_issue
        return await jira_get_issue(issue_key=tool_input.get("issue_key", ""))

    elif tool_name == "jira_search":
        from tools.jira import jira_search
        return await jira_search(
            jql=tool_input.get("jql", ""),
            max_results=int(tool_input.get("max_results", 10)),
        )

    elif tool_name == "jira_create_issue":
        from tools.jira import jira_create_issue
        return await jira_create_issue(
            project_key=tool_input.get("project_key", ""),
            summary=tool_input.get("summary", ""),
            description=tool_input.get("description", ""),
            issue_type=tool_input.get("issue_type", "Task"),
            priority=tool_input.get("priority", "Medium"),
        )

    elif tool_name == "github_get_issue":
        from tools.github_issues import github_get_issue
        return await github_get_issue(
            issue_number=int(tool_input.get("issue_number", 0)),
            repo=tool_input.get("repo", ""),
        )

    elif tool_name == "github_search_issues":
        from tools.github_issues import github_search_issues
        return await github_search_issues(
            query=tool_input.get("query", ""),
            max_results=int(tool_input.get("max_results", 10)),
            repo=tool_input.get("repo", ""),
        )

    elif tool_name == "github_create_issue":
        from tools.github_issues import github_create_issue
        return await github_create_issue(
            title=tool_input.get("title", ""),
            body=tool_input.get("body", ""),
            labels=tool_input.get("labels", []),
            repo=tool_input.get("repo", ""),
        )

    elif tool_name == "servicenow_get_ticket":
        from tools.servicenow import servicenow_get_ticket
        return await servicenow_get_ticket(
            ticket_number=tool_input.get("ticket_number", ""),
            table=tool_input.get("table", ""),
        )

    elif tool_name == "servicenow_search_tickets":
        from tools.servicenow import servicenow_search_tickets
        return await servicenow_search_tickets(
            query=tool_input.get("query", ""),
            max_results=int(tool_input.get("max_results", 10)),
            table=tool_input.get("table", ""),
        )

    elif tool_name == "servicenow_create_ticket":
        from tools.servicenow import servicenow_create_ticket
        return await servicenow_create_ticket(
            short_description=tool_input.get("short_description", ""),
            description=tool_input.get("description", ""),
            urgency=tool_input.get("urgency", "3"),
            impact=tool_input.get("impact", "3"),
            caller_id=tool_input.get("caller_id", ""),
            table=tool_input.get("table", ""),
        )

    elif tool_name.startswith("mcp__") or tool_name.startswith("mcp:"):
        return await execute_mcp_tool(tool_name, tool_input)

    else:
        logger.warning("Unknown tool requested: %r", tool_name)
        return f"❌ Unknown tool: {tool_name!r}"


def get_tool_definitions(tool_names: list[str]) -> list[dict]:
    """
    Return Anthropic-format tool definitions for the given list of tool names.
    Unknown names are silently skipped (with a warning).
    """
    result = []
    result.extend(get_mcp_tool_definitions(tool_names))
    for name in tool_names:
        if name in _TOOL_DEFINITIONS:
            result.append(_TOOL_DEFINITIONS[name])
        else:
            if (
                name == "mcp:*"
                or (name.startswith("mcp:") and name.endswith(":*"))
                or name.startswith("mcp__")
                or (name.startswith("mcp:") and name.count(":") >= 2)
            ):
                continue
            logger.warning("Tool %r not found in registry", name)
    return result


def list_tools() -> list[str]:
    """Return all registered tool names."""
    return list(_TOOL_DEFINITIONS.keys()) + list_mcp_tools()
