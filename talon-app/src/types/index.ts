export type EmployeeStatus = 'active' | 'idle' | 'paused' | 'error';
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type ReactState = 'perceive' | 'plan' | 'act' | 'observe' | 'decide';

export interface EmployeeStats {
  conversations: number;
  messages: number;
  episodicMemories: number;
  entityRecords: number;
  auditEvents: number;
}

export interface DigitalEmployee {
  id: string;
  name: string;
  role: string;
  emoji: string;
  color: string;
  status: EmployeeStatus;
  provider: string;
  model: string;
  tools: string[];
  channels: string[];
  currentTask: string;
  stats: EmployeeStats;
}

export interface ActivityEvent {
  id: string;
  timestamp: Date;
  employeeId: string;
  employeeName: string;
  eventType: string;
  detail: string;
}

export interface AuditEvent {
  id: string;
  timestamp: Date;
  employeeId: string;
  employeeName: string;
  eventType: string;
  action: string;
  detail: string;
  riskLevel: RiskLevel;
  outcome: 'success' | 'failure' | 'pending' | 'rejected';
  conversationId?: string | null;
  userId?: string | null;
}

export interface HitlRequest {
  id: string;
  employeeId: string;
  employeeName: string;
  task: string;
  reason: string;
  riskLevel: RiskLevel;
  timestamp: Date;
  status: 'pending' | 'approved' | 'rejected';
  requestedBy?: string | null;
  note?: string | null;
}

export interface MemoryEntry {
  id: string;
  kind: 'episodic' | 'entity';
  title: string;
  content: string;
  tags: string[];
  timestamp?: Date;
}

export interface EmployeeMemory {
  episodicMemories: MemoryEntry[];
  entityMemories: MemoryEntry[];
}

export interface PolicyRule {
  id: string;
  name: string;
  scope: string;
  pattern: string;
  action: string;
  description: string;
  enabled: boolean;
  priority: number;
  updatedAt: Date;
}

export interface ScheduledJob {
  id: string;
  agentId: string;
  agentName: string;
  name: string;
  prompt: string;
  intervalMinutes: number;
  status: 'active' | 'paused' | 'running';
  lastRunAt?: Date | null;
  nextRunAt?: Date | null;
  lastResult?: string | null;
  lastError?: string | null;
  lastConversationId?: string | null;
}

export interface ScheduledJobRun {
  id: string;
  jobId: string;
  status: string;
  startedAt: Date;
  finishedAt?: Date | null;
  conversationId?: string | null;
  responsePreview?: string | null;
  error?: string | null;
}

export interface AgentCheckpoint {
  id: string;
  agentId: string;
  agentName: string;
  label: string;
  summary: string;
  createdBy?: string | null;
  createdAt: Date;
  stats: {
    conversations: number;
    episodicMemories: number;
    entityRecords: number;
    hitlRequests: number;
    scheduledJobs: number;
  };
}

export interface KillSwitchState {
  active: boolean;
  reason: string;
  updatedBy?: string | null;
  activatedAt?: Date | null;
}

export interface HistoryMessage {
  id: string;
  role: string;
  content: string;
  conversationId: string;
  timestamp: Date;
}

export interface GlobalMetrics {
  totalAgents: number;
  activeAgents: number;
  pausedAgents: number;
  totalConversations: number;
  totalMessages: number;
  totalAuditEvents: number;
  totalEpisodicMemories: number;
  totalEntityRecords: number;
  pendingHitl: number;
  totalScheduledJobs: number;
  activeScheduledJobs: number;
  pausedScheduledJobs: number;
  uptimeSince?: number;
  platformVersion?: string;
}

export interface SystemHealth {
  status: string;
  policyEngine?: {
    engine: string;
    status: string;
    detail: string;
  };
  teamsIntegration: string;
  mcpIntegration?: {
    status: string;
    serversConfigured: number;
    discoveredTools: number;
    detail: string;
  };
  websocketConnections: number;
  providers: Record<string, boolean>;
  killSwitch: KillSwitchState;
}
