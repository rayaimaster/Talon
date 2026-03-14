# Project Talon Implementation Plan

This document is the current implementation plan for Project Talon.

It now has two purposes:

- record what has already been completed
- define the remaining TODO list, including the commander-led multi-agent scenario

## Completed Work

The following major platform work is already complete in the current codebase:

- Render deployment path for `talon-backend` and `talon-webchat`
- local run and deployment documentation
- real-time webchat with agent selection, history loading, and streamed tool events
- backend conversation memory, episodic memory, entity memory, and audit persistence
- multi-provider LLM support for Anthropic, OpenAI-compatible/local, and Gemini
- real admin/control-plane APIs and UI
- HITL workflow with persisted requests and operator approve/reject actions
- backend-managed policy rules
- optional OPA/Rego policy evaluation
- recurring scheduling and worker execution
- checkpointing and rollback
- global kill switch
- Microsoft Teams productionization
- Jira productionization
- GitHub Issues productionization
- ServiceNow productionization
- MCP tool integration

## Priority Meanings

- `P0`: required to make the commander-led operating model real
- `P1`: important platform maturity work after the core commander workflow exists
- `P2`: scale, resilience, and verification hardening

## P0: Commander-Led Multi-Agent Workflow

### 1. Add first-class task handoff and delegation

Goal:

- let one digital employee create work for another digital employee

TODO:

- add a persisted task entity with:
  - source ticket or source incident
  - assigned employee
  - status
  - priority
  - due date
  - execution notes
  - approval state
- add APIs to:
  - create tasks
  - assign or reassign tasks
  - list tasks by employee
  - update task status
  - attach execution results
- add audit events for:
  - task created
  - task assigned
  - task started
  - task blocked
  - task completed
- add UI views in `talon-app` for:
  - commander task queue
  - per-employee task inbox
  - task history and current state

### 2. Add a concrete commander workflow

Goal:

- let a human commander supervise the specialized employees as one coordinated operating model

TODO:

- add a commander-facing orchestration view in `talon-app`
- show:
  - incoming tickets
  - open delegated tasks
  - incidents needing triage
  - renewals due soon
  - approvals waiting in HITL
- add commander actions for:
  - approve task plans
  - reassign work
  - pause one workflow without killing the whole platform
  - trigger manual retries
  - escalate to HITL

### 3. Add the four scenario agents

Goal:

- make your scenario concrete in the shipped configuration

TODO:

- add a ticket review employee config
- add a task execution employee config
- add an incident triage employee config
- add a renewal guard employee config
- define:
  - role-specific system prompts
  - tool grants
  - policy scopes
  - scheduler jobs
  - HITL thresholds

### 4. Implement ticket review to task creation flow

Goal:

- let the first employee review request tickets and create execution tasks

TODO:

- add a formal task-plan output shape
- let the ticket review employee:
  - read Jira, GitHub Issues, ServiceNow, or MCP-backed request sources
  - summarize request scope
  - split work into tasks
  - create delegated tasks for the execution employee
- add policy/HITL checks before task plans are committed when risk is high

### 5. Implement task execution flow

Goal:

- let the second employee execute approved tasks and write back results

TODO:

- let the task execution employee claim assigned tasks
- add controlled execution states:
  - ready
  - waiting_approval
  - executing
  - blocked
  - done
- write execution results back to:
  - the Talon task record
  - the source ticketing system
  - audit history
- support safe execution through:
  - shell
  - ServiceNow
  - GitHub Issues
  - MCP-backed tools

### 6. Implement incident watch and triage flow

Goal:

- let the third employee monitor incidents and triage them automatically

TODO:

- add at least one real incident-source integration
  - recommended first options:
    - MCP-backed monitoring tool
    - Sentry
    - PagerDuty
- add scheduled polling or event-ingestion workflows
- let the incident triage employee:
  - classify severity
  - correlate with known tasks or prior incidents
  - create/update incident tickets
  - delegate follow-up tasks
  - escalate critical incidents to the commander

### 7. Implement renewal watch and renewal execution flow

Goal:

- let the fourth employee watch expiry windows and handle renewals

TODO:

- add at least one real expiry-source integration for:
  - certificates
  - secrets
  - passwords
  - tokens
- add renewal windows and alert thresholds
- let the renewal guard employee:
  - create renewal tasks automatically
  - perform safe renewals where automation is allowed
  - request HITL approval for sensitive renewals
  - escalate failed or manual renewals

## P1: Platform Maturity After Commander Workflow

### 8. Expand observability beyond health/activity/audit

TODO:

- add real time-series metrics for:
  - latency
  - token usage
  - model/provider usage
  - tool usage
  - cost estimates
  - scheduler throughput and failures
  - delegated task throughput and failure rate

### 9. Add deeper operator modes

TODO:

- implement:
  - read-only mode
  - supervised execution mode
  - tool-restricted mode
  - maintenance mode per employee
- make these modes visible in:
  - health
  - audit history
  - task queue UI
  - scheduled execution

### 10. Tighten OPA operations

TODO:

- add last successful sync time
- add failure detail and operator guidance
- add policy bundle version history in audit events

## P2: Scale, Resilience, and Verification

### 11. Replace SQLite with a multi-instance-safe datastore

TODO:

- move persistence to Postgres or equivalent
- add migration support
- preserve current state models for:
  - conversations
  - memory
  - audit
  - HITL
  - policy
  - tasks
  - schedules
  - checkpoints
  - system state

### 12. Define backup, restore, and migration operations

TODO:

- add explicit backup and restore procedures
- document environment promotion and migration paths

### 13. Broaden automated verification

TODO:

- add frontend behavioral tests for:
  - webchat
  - admin console
  - commander workflow
  - task handoff
  - incident triage
  - renewal workflow
- add integration tests for:
  - OPA mode
  - Teams
  - Jira
  - GitHub Issues
  - ServiceNow
  - MCP-backed tools

### 14. Add end-to-end deployment smoke tests

TODO:

- verify backend, webchat, admin console, Teams, Jira, GitHub Issues, ServiceNow, MCP, and OPA together
- add post-deploy checks for:
  - health payloads
  - commander workflow state
  - delegated task execution
  - one complete ticket-to-task-to-execution round-trip

## Recommended Delivery Order

1. `P0.1` task handoff and delegation
2. `P0.2` commander orchestration view
3. `P0.3` add the four scenario employees
4. `P0.4` ticket review to task creation flow
5. `P0.5` task execution flow
6. `P0.6` incident watch and triage
7. `P0.7` renewal watch and renewal execution
8. `P1.8` observability expansion
9. `P1.9` deeper operator modes
10. `P1.10` tighter OPA operations
11. `P2.11` replace SQLite
12. `P2.12` backup, restore, and migration
13. `P2.13` broader automated verification
14. `P2.14` end-to-end deployment smoke tests

## Bottom Line

Project Talon already delivers the core platform, control plane, governance model, ticketing integrations, and MCP extensibility needed to support this direction.

The biggest remaining work for your scenario is not basic infrastructure anymore. It is adding:

- first-class multi-agent delegation
- persistent task handoff
- incident-source integrations
- expiry/renewal integrations
- commander-specific workflow views
