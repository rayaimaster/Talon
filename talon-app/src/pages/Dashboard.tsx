import { Activity, Brain, ClipboardList, MessageSquare, ShieldCheck, Users } from 'lucide-react';
import { MetricCard, PageHeader, PrototypeNotice, StatusBadge, SurfaceCard } from '../components/UI';
import { useApp } from '../context/AppContext';

function ProviderSummary({ providers }: { providers: Record<string, boolean> }) {
  const entries = Object.entries(providers);

  return (
    <SurfaceCard className="p-4">
      <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
        <ShieldCheck className="h-4 w-4 text-green-400" />
        Provider Health
      </h2>
      <div className="space-y-3">
        {entries.length === 0 && <p className="text-sm text-slate-400">No provider status reported yet.</p>}
        {entries.map(([provider, enabled]) => (
          <div key={provider} className="flex items-center justify-between">
            <span className="text-sm text-slate-300 capitalize">{provider}</span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${enabled ? 'bg-green-500/15 text-green-300' : 'bg-slate-700 text-slate-400'}`}>
              {enabled ? 'Configured' : 'Missing key'}
            </span>
          </div>
        ))}
      </div>
    </SurfaceCard>
  );
}

export default function Dashboard() {
  const { employees, activityFeed, globalMetrics, systemHealth, isLoading } = useApp();

  return (
    <div>
      <PageHeader
        title="Platform Dashboard"
        subtitle="Backend-backed overview of live agents, message volume, memory footprint, and recent platform activity."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-6">
        <MetricCard
          title="Agents"
          value={globalMetrics.totalAgents}
          subtitle={`${globalMetrics.activeAgents} active · ${globalMetrics.pausedAgents} paused`}
          icon={<Users className="h-5 w-5" />}
          color="blue"
        />
        <MetricCard
          title="Messages"
          value={globalMetrics.totalMessages.toLocaleString()}
          subtitle={`${globalMetrics.totalConversations} conversations`}
          icon={<MessageSquare className="h-5 w-5" />}
          color="green"
        />
        <MetricCard
          title="Audit Events"
          value={globalMetrics.totalAuditEvents.toLocaleString()}
          icon={<ClipboardList className="h-5 w-5" />}
          color="purple"
        />
        <MetricCard
          title="Episodic Memory"
          value={globalMetrics.totalEpisodicMemories.toLocaleString()}
          icon={<Brain className="h-5 w-5" />}
          color="yellow"
        />
        <MetricCard
          title="Entity Records"
          value={globalMetrics.totalEntityRecords.toLocaleString()}
          icon={<Brain className="h-5 w-5" />}
          color="orange"
        />
        <MetricCard
          title="Pending HITL"
          value={globalMetrics.pendingHitl}
          subtitle={isLoading ? 'Refreshing...' : 'Current queue depth'}
          icon={<ShieldCheck className="h-5 w-5" />}
          color="red"
        />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <SurfaceCard className="xl:col-span-2 p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <Users className="h-4 w-4 text-blue-400" />
            Agent Status
          </h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {employees.map((employee) => (
              <div key={employee.id} className="rounded-xl border border-slate-700/60 bg-slate-900/60 p-4">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className="flex h-11 w-11 items-center justify-center rounded-2xl border text-xl"
                      style={{ borderColor: `${employee.color}50`, backgroundColor: `${employee.color}18` }}
                    >
                      {employee.emoji}
                    </div>
                    <div>
                      <div className="font-semibold text-white">{employee.name}</div>
                      <div className="text-xs font-medium" style={{ color: employee.color }}>
                        {employee.role}
                      </div>
                    </div>
                  </div>
                  <StatusBadge status={employee.status} />
                </div>
                <p className="mb-4 text-sm text-slate-400">{employee.currentTask}</p>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded-lg bg-slate-800/80 px-2 py-2">
                    <div className="font-semibold text-white">{employee.stats.conversations}</div>
                    <div className="text-slate-500">Conversations</div>
                  </div>
                  <div className="rounded-lg bg-slate-800/80 px-2 py-2">
                    <div className="font-semibold text-white">{employee.stats.messages}</div>
                    <div className="text-slate-500">Messages</div>
                  </div>
                  <div className="rounded-lg bg-slate-800/80 px-2 py-2">
                    <div className="font-semibold text-white">{employee.stats.auditEvents}</div>
                    <div className="text-slate-500">Audit</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </SurfaceCard>

        <div className="space-y-6">
          <SurfaceCard className="p-4">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
              <Activity className="h-4 w-4 text-blue-400" />
              API Health
            </h2>
            <div className="space-y-3 text-sm text-slate-300">
              <div className="flex items-center justify-between">
                <span>Status</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${systemHealth.status === 'ok' ? 'bg-green-500/15 text-green-300' : 'bg-red-500/15 text-red-300'}`}>
                  {systemHealth.status}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Teams Integration</span>
                <span className="text-slate-400">{systemHealth.teamsIntegration}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>WebSocket Connections</span>
                <span className="text-white">{systemHealth.websocketConnections}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Platform Version</span>
                <span className="text-white">{globalMetrics.platformVersion ?? 'unknown'}</span>
              </div>
            </div>
          </SurfaceCard>

          <ProviderSummary providers={systemHealth.providers} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <SurfaceCard className="xl:col-span-2 p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <Activity className="h-4 w-4 text-green-400" />
            Recent Activity
          </h2>
          <div className="space-y-3">
            {activityFeed.length === 0 && <p className="text-sm text-slate-400">No recent activity yet.</p>}
            {activityFeed.map((event) => (
              <div key={event.id} className="rounded-xl border border-slate-700/40 bg-slate-900/50 p-3">
                <div className="mb-1 flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-white">{event.employeeName}</div>
                  <div className="text-xs text-slate-500">{event.timestamp.toLocaleString()}</div>
                </div>
                <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">{event.eventType}</div>
                <div className="text-sm text-slate-300">{event.detail}</div>
              </div>
            ))}
          </div>
        </SurfaceCard>

        <PrototypeNotice
          title="Frontend charts were intentionally de-scoped"
          description="This dashboard now shows live backend data. The previous synthetic charts and derived KPIs were removed until the backend exposes real time-series telemetry."
        />
      </div>
    </div>
  );
}
