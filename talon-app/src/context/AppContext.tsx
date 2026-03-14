import { createContext, ReactNode, useContext, useEffect, useState } from 'react';
import {
  ActivityEvent,
  AgentCheckpoint,
  AuditEvent,
  DigitalEmployee,
  EmployeeMemory,
  GlobalMetrics,
  HistoryMessage,
  HitlRequest,
  KillSwitchState,
  PolicyRule,
  RiskLevel,
  ScheduledJob,
  ScheduledJobRun,
  SystemHealth,
} from '../types';
import { clearStoredConfig, getStoredConfig, saveStoredConfig, StoredConfig } from '../config';

interface AppState {
  employees: DigitalEmployee[];
  activityFeed: ActivityEvent[];
  auditEvents: AuditEvent[];
  hitlRequests: HitlRequest[];
  policyRules: PolicyRule[];
  scheduledJobs: ScheduledJob[];
  checkpoints: AgentCheckpoint[];
  globalMetrics: GlobalMetrics;
  systemHealth: SystemHealth;
  selectedEmployeeId: string | null;
  config: StoredConfig;
  isConfigured: boolean;
  isLoading: boolean;
  error: string | null;
}

interface CreateHitlInput {
  agentId: string;
  task: string;
  reason: string;
  riskLevel: RiskLevel;
  requestedBy?: string;
}

interface AppContextType extends AppState {
  selectEmployee: (id: string | null) => void;
  setConnection: (apiBaseUrl: string, adminToken: string) => void;
  clearConnection: () => void;
  refresh: () => Promise<void>;
  pauseEmployee: (id: string) => Promise<void>;
  resumeEmployee: (id: string) => Promise<void>;
  approveHitl: (id: string, note?: string) => Promise<void>;
  rejectHitl: (id: string, note?: string) => Promise<void>;
  createHitl: (input: CreateHitlInput) => Promise<void>;
  togglePolicyRule: (id: string, enabled: boolean) => Promise<void>;
  createScheduledJob: (input: {
    agentId: string;
    name: string;
    prompt: string;
    intervalMinutes: number;
    startImmediately?: boolean;
  }) => Promise<void>;
  pauseScheduledJob: (id: string) => Promise<void>;
  resumeScheduledJob: (id: string) => Promise<void>;
  runScheduledJobNow: (id: string) => Promise<void>;
  loadScheduledJobRuns: (id: string, limit?: number) => Promise<ScheduledJobRun[]>;
  createCheckpoint: (input: {
    agentId: string;
    label: string;
    summary?: string;
    createdBy?: string;
  }) => Promise<void>;
  restoreCheckpoint: (id: string, input?: {
    createdBy?: string;
    createSafetyCheckpoint?: boolean;
  }) => Promise<void>;
  setKillSwitch: (input: {
    active: boolean;
    reason?: string;
    updatedBy?: string;
  }) => Promise<void>;
  loadEmployeeMemory: (id: string, limit?: number) => Promise<EmployeeMemory>;
  loadEmployeeHistory: (id: string, limit?: number) => Promise<HistoryMessage[]>;
}

const DEFAULT_METRICS: GlobalMetrics = {
  totalAgents: 0,
  activeAgents: 0,
  pausedAgents: 0,
  totalConversations: 0,
  totalMessages: 0,
  totalAuditEvents: 0,
  totalEpisodicMemories: 0,
  totalEntityRecords: 0,
  pendingHitl: 0,
  totalScheduledJobs: 0,
  activeScheduledJobs: 0,
  pausedScheduledJobs: 0,
};

const DEFAULT_HEALTH: SystemHealth = {
  status: 'unknown',
  policyEngine: {
    engine: 'legacy',
    status: 'unknown',
    detail: '',
  },
  teamsIntegration: 'unknown',
  mcpIntegration: {
    status: 'disabled',
    serversConfigured: 0,
    discoveredTools: 0,
    detail: '',
  },
  websocketConnections: 0,
  providers: {},
  killSwitch: {
    active: false,
    reason: '',
    updatedBy: null,
    activatedAt: null,
  },
};

const COLOR_FALLBACK = '#64748B';
const REFRESH_INTERVAL_MS = 15000;

const AppContext = createContext<AppContextType | null>(null);

function inferOutcome(eventType: string): AuditEvent['outcome'] {
  if (eventType.includes('rejected') || eventType.includes('blocked') || eventType.includes('error')) {
    return 'failure';
  }
  if (eventType.includes('requested')) {
    return 'pending';
  }
  return 'success';
}

function inferRisk(eventType: string): RiskLevel {
  if (eventType.includes('blocked') || eventType.includes('security')) {
    return 'high';
  }
  if (eventType.includes('hitl') || eventType.includes('paused') || eventType.includes('resumed')) {
    return 'medium';
  }
  return 'low';
}

function stringifyContent(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => stringifyContent(item)).join('\n');
  }

  if (value && typeof value === 'object') {
    const maybeText = (value as { text?: unknown }).text;
    if (typeof maybeText === 'string') {
      return maybeText;
    }
    return JSON.stringify(value);
  }

  return String(value ?? '');
}

function employeeTaskLabel(
  employee: { status: string; stats: { conversations: number; messages: number } },
  latestActivity?: ActivityEvent,
): string {
  if (employee.status === 'paused') {
    return 'Paused by operator';
  }
  if (latestActivity) {
    return latestActivity.detail;
  }
  if (employee.stats.messages > 0) {
    return 'Ready for the next request';
  }
  return 'No conversation history yet';
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<StoredConfig>(() => getStoredConfig());
  const [employees, setEmployees] = useState<DigitalEmployee[]>([]);
  const [activityFeed, setActivityFeed] = useState<ActivityEvent[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [hitlRequests, setHitlRequests] = useState<HitlRequest[]>([]);
  const [policyRules, setPolicyRules] = useState<PolicyRule[]>([]);
  const [scheduledJobs, setScheduledJobs] = useState<ScheduledJob[]>([]);
  const [checkpoints, setCheckpoints] = useState<AgentCheckpoint[]>([]);
  const [globalMetrics, setGlobalMetrics] = useState<GlobalMetrics>(DEFAULT_METRICS);
  const [systemHealth, setSystemHealth] = useState<SystemHealth>(DEFAULT_HEALTH);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isConfigured = Boolean(config.apiBaseUrl && config.adminToken);

  async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
    if (!config.apiBaseUrl || !config.adminToken) {
      throw new Error('Configure the backend URL and admin token first.');
    }

    const response = await fetch(`${config.apiBaseUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Token': config.adminToken,
        ...(init?.headers ?? {}),
      },
    });

    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (typeof body?.detail === 'string') {
          detail = body.detail;
        }
      } catch {
        // Ignore JSON parse failures and use the HTTP status text.
      }
      throw new Error(detail);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  }

  async function refresh() {
    if (!isConfigured) {
      return;
    }

    setIsLoading(true);

    try {
      const [metricsRes, employeesRes, activityRes, auditRes, hitlRes, policyRes, schedulesRes, checkpointsRes, healthRes] = await Promise.all([
        apiFetch<{
          agents: { total: number; active: number; paused: number };
          conversations: { total: number };
          messages: { total: number };
          audit_events: { total: number };
          memory: { episodic: number; entities: number };
          hitl: { pending: number };
          scheduled_jobs: { total: number; active: number; paused: number };
          platform: { uptime_since: number; version: string };
        }>('/api/dashboard/metrics'),
        apiFetch<{
          employees: Array<{
            id: string;
            name: string;
            role: string;
            emoji: string;
            color: string;
            status: 'active' | 'paused';
            provider?: string;
            model?: string;
            tools?: string[];
            channels?: string[];
            stats: {
              conversations: number;
              messages: number;
              episodic_memories?: number;
              entity_records?: number;
              audit_events?: number;
            };
          }>;
        }>('/api/dashboard/employees'),
        apiFetch<{
          activities: Array<{
            id: number;
            timestamp: number;
            agent_id: string;
            agent_name: string;
            event_type: string;
            details: Record<string, unknown>;
          }>;
        }>('/api/dashboard/activity?limit=40'),
        apiFetch<{
          events: Array<{
            id: number;
            timestamp: number;
            agent_id: string;
            event_type: string;
            user_id?: string | null;
            conversation_id?: string | null;
            details: Record<string, unknown>;
          }>;
        }>('/api/audit/events?limit=100'),
        apiFetch<{
          requests: Array<{
            id: number;
            agent_id: string;
            agent_name: string;
            task: string;
            reason: string;
            risk_level: RiskLevel;
            status: 'pending' | 'approved' | 'rejected';
            requested_by?: string | null;
            resolution_note?: string | null;
            created_at: number;
          }>;
        }>('/api/hitl/requests?limit=100'),
        apiFetch<{
          rules: Array<{
            id: string;
            name: string;
            scope: string;
            pattern: string;
            action: string;
            description: string;
            enabled: boolean;
            priority: number;
            updated_at: number;
          }>;
        }>('/api/policy/rules'),
        apiFetch<{
          jobs: Array<{
            id: number;
            agent_id: string;
            agent_name: string;
            name: string;
            prompt: string;
            interval_minutes: number;
            status: 'active' | 'paused' | 'running';
            last_run_at?: number | null;
            next_run_at?: number | null;
            last_result?: string | null;
            last_error?: string | null;
            last_conversation_id?: string | null;
          }>;
        }>('/api/schedules/jobs'),
        apiFetch<{
          checkpoints: Array<{
            id: number;
            agent_id: string;
            agent_name: string;
            label: string;
            summary: string;
            created_by?: string | null;
            created_at: number;
            stats: {
              conversations: number;
              episodic_memories: number;
              entity_records: number;
              hitl_requests: number;
              scheduled_jobs: number;
            };
          }>;
        }>('/api/checkpoints'),
        fetch(`${config.apiBaseUrl}/api/health`).then(async (response) => {
          if (!response.ok) {
            throw new Error(`${response.status} ${response.statusText}`);
          }
          return response.json() as Promise<{
            status: string;
            policy_engine?: {
              engine: string;
              status: string;
              detail: string;
            };
            teams_integration: string;
            mcp_integration?: {
              status: string;
              servers_configured: number;
              discovered_tools: number;
              detail: string;
            };
            websocket_connections: number;
            providers: Record<string, boolean>;
            kill_switch: {
              active: boolean;
              reason: string;
              updated_by?: string | null;
              activated_at?: number | null;
            };
          }>;
        }),
      ]);

      const mappedActivity: ActivityEvent[] = activityRes.activities.map((event) => ({
        id: String(event.id),
        timestamp: new Date(event.timestamp * 1000),
        employeeId: event.agent_id,
        employeeName: event.agent_name,
        eventType: event.event_type,
        detail:
          typeof event.details?.task === 'string'
            ? event.details.task
            : typeof event.details?.reason === 'string'
              ? event.details.reason
            : event.event_type.replace(/_/g, ' '),
      }));

      const latestActivityByEmployee = new Map<string, ActivityEvent>();
      for (const event of mappedActivity) {
        if (!latestActivityByEmployee.has(event.employeeId)) {
          latestActivityByEmployee.set(event.employeeId, event);
        }
      }

      const mappedEmployees: DigitalEmployee[] = employeesRes.employees.map((employee) => ({
        id: employee.id,
        name: employee.name,
        role: employee.role,
        emoji: employee.emoji || '🤖',
        color: employee.color || COLOR_FALLBACK,
        status: employee.status === 'paused' ? 'paused' : 'active',
        provider: employee.provider ?? 'anthropic',
        model: employee.model ?? 'unknown',
        tools: employee.tools ?? [],
        channels: employee.channels ?? [],
        currentTask: employeeTaskLabel(
          {
            status: employee.status,
            stats: {
              conversations: employee.stats?.conversations ?? 0,
              messages: employee.stats?.messages ?? 0,
            },
          },
          latestActivityByEmployee.get(employee.id),
        ),
        stats: {
          conversations: employee.stats?.conversations ?? 0,
          messages: employee.stats?.messages ?? 0,
          episodicMemories: employee.stats?.episodic_memories ?? 0,
          entityRecords: employee.stats?.entity_records ?? 0,
          auditEvents: employee.stats?.audit_events ?? 0,
        },
      }));

      const employeeNameById = new Map(mappedEmployees.map((employee) => [employee.id, employee.name]));

      setActivityFeed(mappedActivity);
      setEmployees(mappedEmployees);
      setAuditEvents(
        auditRes.events.map((event) => ({
          id: String(event.id),
          timestamp: new Date(event.timestamp * 1000),
          employeeId: event.agent_id,
          employeeName: employeeNameById.get(event.agent_id) ?? event.agent_id,
          eventType: event.event_type,
          action: typeof event.details?.task === 'string' ? event.details.task : event.event_type.replace(/_/g, ' '),
          detail: JSON.stringify(event.details ?? {}),
          riskLevel: inferRisk(event.event_type),
          outcome: inferOutcome(event.event_type),
          conversationId: event.conversation_id,
          userId: event.user_id,
        })),
      );
      setHitlRequests(
        hitlRes.requests.map((request) => ({
          id: String(request.id),
          employeeId: request.agent_id,
          employeeName: request.agent_name,
          task: request.task,
          reason: request.reason,
          riskLevel: request.risk_level,
          timestamp: new Date(request.created_at * 1000),
          status: request.status,
          requestedBy: request.requested_by,
          note: request.resolution_note,
        })),
      );
      setPolicyRules(
        policyRes.rules.map((rule) => ({
          id: rule.id,
          name: rule.name,
          scope: rule.scope,
          pattern: rule.pattern,
          action: rule.action,
          description: rule.description,
          enabled: rule.enabled,
          priority: rule.priority,
          updatedAt: new Date(rule.updated_at * 1000),
        })),
      );
      setScheduledJobs(
        schedulesRes.jobs.map((job) => ({
          id: String(job.id),
          agentId: job.agent_id,
          agentName: job.agent_name,
          name: job.name,
          prompt: job.prompt,
          intervalMinutes: job.interval_minutes,
          status: job.status,
          lastRunAt: job.last_run_at ? new Date(job.last_run_at * 1000) : null,
          nextRunAt: job.next_run_at ? new Date(job.next_run_at * 1000) : null,
          lastResult: job.last_result,
          lastError: job.last_error,
          lastConversationId: job.last_conversation_id,
        })),
      );
      setCheckpoints(
        checkpointsRes.checkpoints.map((checkpoint) => ({
          id: String(checkpoint.id),
          agentId: checkpoint.agent_id,
          agentName: checkpoint.agent_name,
          label: checkpoint.label,
          summary: checkpoint.summary,
          createdBy: checkpoint.created_by,
          createdAt: new Date(checkpoint.created_at * 1000),
          stats: {
            conversations: checkpoint.stats.conversations,
            episodicMemories: checkpoint.stats.episodic_memories,
            entityRecords: checkpoint.stats.entity_records,
            hitlRequests: checkpoint.stats.hitl_requests,
            scheduledJobs: checkpoint.stats.scheduled_jobs,
          },
        })),
      );
      setGlobalMetrics({
        totalAgents: metricsRes.agents.total,
        activeAgents: metricsRes.agents.active,
        pausedAgents: metricsRes.agents.paused,
        totalConversations: metricsRes.conversations.total,
        totalMessages: metricsRes.messages.total,
        totalAuditEvents: metricsRes.audit_events.total,
        totalEpisodicMemories: metricsRes.memory.episodic,
        totalEntityRecords: metricsRes.memory.entities,
        pendingHitl: metricsRes.hitl.pending,
        totalScheduledJobs: metricsRes.scheduled_jobs.total,
        activeScheduledJobs: metricsRes.scheduled_jobs.active,
        pausedScheduledJobs: metricsRes.scheduled_jobs.paused,
        uptimeSince: metricsRes.platform.uptime_since,
        platformVersion: metricsRes.platform.version,
      });
      setSystemHealth({
        status: healthRes.status,
        policyEngine: healthRes.policy_engine
          ? {
              engine: healthRes.policy_engine.engine,
              status: healthRes.policy_engine.status,
              detail: healthRes.policy_engine.detail,
            }
          : DEFAULT_HEALTH.policyEngine,
        teamsIntegration: healthRes.teams_integration,
        mcpIntegration: healthRes.mcp_integration
          ? {
              status: healthRes.mcp_integration.status,
              serversConfigured: healthRes.mcp_integration.servers_configured,
              discoveredTools: healthRes.mcp_integration.discovered_tools,
              detail: healthRes.mcp_integration.detail,
            }
          : DEFAULT_HEALTH.mcpIntegration,
        websocketConnections: healthRes.websocket_connections,
        providers: healthRes.providers,
        killSwitch: {
          active: healthRes.kill_switch.active,
          reason: healthRes.kill_switch.reason,
          updatedBy: healthRes.kill_switch.updated_by,
          activatedAt: healthRes.kill_switch.activated_at
            ? new Date(healthRes.kill_switch.activated_at * 1000)
            : null,
        },
      });
      setError(null);
      setSelectedEmployeeId((current) => {
        if (current && mappedEmployees.some((employee) => employee.id === current)) {
          return current;
        }
        return mappedEmployees[0]?.id ?? null;
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown dashboard error';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!isConfigured) {
      return;
    }

    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, REFRESH_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [config.apiBaseUrl, config.adminToken, isConfigured]);

  async function pauseEmployee(id: string) {
    await apiFetch(`/api/employees/${id}/pause`, { method: 'POST' });
    await refresh();
  }

  async function resumeEmployee(id: string) {
    await apiFetch(`/api/employees/${id}/resume`, { method: 'POST' });
    await refresh();
  }

  async function approveHitl(id: string, note?: string) {
    await apiFetch(`/api/hitl/requests/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    });
    await refresh();
  }

  async function rejectHitl(id: string, note?: string) {
    await apiFetch(`/api/hitl/requests/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    });
    await refresh();
  }

  async function createHitl(input: CreateHitlInput) {
    await apiFetch('/api/hitl/requests', {
      method: 'POST',
      body: JSON.stringify({
        agent_id: input.agentId,
        task: input.task,
        reason: input.reason,
        risk_level: input.riskLevel,
        requested_by: input.requestedBy,
      }),
    });
    await refresh();
  }

  async function togglePolicyRule(id: string, enabled: boolean) {
    await apiFetch(`/api/policy/rules/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    });
    await refresh();
  }

  async function createScheduledJob(input: {
    agentId: string;
    name: string;
    prompt: string;
    intervalMinutes: number;
    startImmediately?: boolean;
  }) {
    await apiFetch('/api/schedules/jobs', {
      method: 'POST',
      body: JSON.stringify({
        agent_id: input.agentId,
        name: input.name,
        prompt: input.prompt,
        interval_minutes: input.intervalMinutes,
        start_immediately: input.startImmediately ?? false,
      }),
    });
    await refresh();
  }

  async function pauseScheduledJob(id: string) {
    await apiFetch(`/api/schedules/jobs/${id}/pause`, { method: 'POST' });
    await refresh();
  }

  async function resumeScheduledJob(id: string) {
    await apiFetch(`/api/schedules/jobs/${id}/resume`, { method: 'POST' });
    await refresh();
  }

  async function runScheduledJobNow(id: string) {
    await apiFetch(`/api/schedules/jobs/${id}/run`, { method: 'POST' });
    await refresh();
  }

  async function loadScheduledJobRuns(id: string, limit = 20): Promise<ScheduledJobRun[]> {
    const response = await apiFetch<{
      runs: Array<{
        id: number;
        job_id: number;
        status: string;
        started_at: number;
        finished_at?: number | null;
        conversation_id?: string | null;
        response_preview?: string | null;
        error?: string | null;
      }>;
    }>(`/api/schedules/jobs/${id}/runs?limit=${limit}`);

    return response.runs.map((run) => ({
      id: String(run.id),
      jobId: String(run.job_id),
      status: run.status,
      startedAt: new Date(run.started_at * 1000),
      finishedAt: run.finished_at ? new Date(run.finished_at * 1000) : null,
      conversationId: run.conversation_id,
      responsePreview: run.response_preview,
      error: run.error,
    }));
  }

  async function createCheckpoint(input: {
    agentId: string;
    label: string;
    summary?: string;
    createdBy?: string;
  }) {
    await apiFetch('/api/checkpoints', {
      method: 'POST',
      body: JSON.stringify({
        agent_id: input.agentId,
        label: input.label,
        summary: input.summary ?? '',
        created_by: input.createdBy,
      }),
    });
    await refresh();
  }

  async function restoreCheckpoint(id: string, input?: {
    createdBy?: string;
    createSafetyCheckpoint?: boolean;
  }) {
    await apiFetch(`/api/checkpoints/${id}/restore`, {
      method: 'POST',
      body: JSON.stringify({
        created_by: input?.createdBy,
        create_safety_checkpoint: input?.createSafetyCheckpoint ?? true,
      }),
    });
    await refresh();
  }

  async function setKillSwitch(input: {
    active: boolean;
    reason?: string;
    updatedBy?: string;
  }) {
    await apiFetch('/api/system/kill-switch', {
      method: 'POST',
      body: JSON.stringify({
        active: input.active,
        reason: input.reason ?? '',
        updated_by: input.updatedBy,
      }),
    });
    await refresh();
  }

  async function loadEmployeeMemory(id: string, limit = 20): Promise<EmployeeMemory> {
    const response = await apiFetch<{
      episodic_memories: Array<{ summary: string; tags: string[]; timestamp: number }>;
      entity_memories: Array<{ entity_name: string; entity_type: string; facts: Record<string, unknown>; updated_at: number }>;
    }>(`/api/employees/${id}/memory?limit=${limit}`);

    return {
      episodicMemories: response.episodic_memories.map((entry, index) => ({
        id: `episodic-${index}-${entry.timestamp}`,
        kind: 'episodic',
        title: 'Episodic memory',
        content: entry.summary,
        tags: entry.tags,
        timestamp: new Date(entry.timestamp * 1000),
      })),
      entityMemories: response.entity_memories.map((entry, index) => ({
        id: `entity-${index}-${entry.entity_name}`,
        kind: 'entity',
        title: `${entry.entity_name} (${entry.entity_type})`,
        content: JSON.stringify(entry.facts, null, 2),
        tags: [entry.entity_type],
        timestamp: new Date(entry.updated_at * 1000),
      })),
    };
  }

  async function loadEmployeeHistory(id: string, limit = 50): Promise<HistoryMessage[]> {
    const response = await apiFetch<{
      messages: Array<{
        conversation_id: string;
        role: string;
        content: unknown;
        timestamp: number;
      }>;
    }>(`/api/employees/${id}/history?limit=${limit}`);

    return response.messages.map((message, index) => ({
      id: `${message.conversation_id}-${index}-${message.timestamp}`,
      role: message.role,
      content: stringifyContent(message.content),
      conversationId: message.conversation_id,
      timestamp: new Date(message.timestamp * 1000),
    }));
  }

  function setConnection(apiBaseUrl: string, adminToken: string) {
    const saved = saveStoredConfig({ apiBaseUrl, adminToken });
    setConfig(saved);
  }

  function resetConnection() {
    clearStoredConfig();
    setConfig({ apiBaseUrl: '', adminToken: '' });
    setEmployees([]);
    setActivityFeed([]);
    setAuditEvents([]);
    setHitlRequests([]);
    setPolicyRules([]);
    setScheduledJobs([]);
    setCheckpoints([]);
    setGlobalMetrics(DEFAULT_METRICS);
    setSystemHealth(DEFAULT_HEALTH);
    setSelectedEmployeeId(null);
    setError(null);
  }

  return (
    <AppContext.Provider
      value={{
        employees,
        activityFeed,
        auditEvents,
        hitlRequests,
        policyRules,
        scheduledJobs,
        checkpoints,
        globalMetrics,
        systemHealth,
        selectedEmployeeId,
        config,
        isConfigured,
        isLoading,
        error,
        selectEmployee: setSelectedEmployeeId,
        setConnection,
        clearConnection: resetConnection,
        refresh,
        pauseEmployee,
        resumeEmployee,
        approveHitl,
        rejectHitl,
        createHitl,
        togglePolicyRule,
        createScheduledJob,
        pauseScheduledJob,
        resumeScheduledJob,
        runScheduledJobNow,
        loadScheduledJobRuns,
        createCheckpoint,
        restoreCheckpoint,
        setKillSwitch,
        loadEmployeeMemory,
        loadEmployeeHistory,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error('useApp must be used within AppProvider');
  }
  return ctx;
}
