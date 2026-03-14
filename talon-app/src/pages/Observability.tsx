import { Activity, AlertTriangle, Radio, ShieldCheck } from 'lucide-react';
import { PageHeader, PrototypeNotice, SurfaceCard } from '../components/UI';
import { useApp } from '../context/AppContext';

export default function Observability() {
  const { systemHealth, auditEvents, activityFeed, globalMetrics } = useApp();

  return (
    <div>
      <PageHeader
        title="Observability"
        subtitle="This page now reports the health and event streams the backend actually exposes."
      />

      <PrototypeNotice
        title="Time-series telemetry is not implemented yet"
        description="Synthetic charts were removed. When the backend exposes real latency, token, cost, and tool-usage series, they can come back as live graphs instead of placeholders."
      />

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <SurfaceCard className="p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <ShieldCheck className="h-4 w-4 text-green-400" />
            Service Health
          </h2>
          <div className="space-y-3 text-sm text-slate-300">
            <div className="flex items-center justify-between">
              <span>API status</span>
              <span className={systemHealth.status === 'ok' ? 'text-green-300' : 'text-red-300'}>{systemHealth.status}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Teams integration</span>
              <span>{systemHealth.teamsIntegration}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>WebSocket connections</span>
              <span>{systemHealth.websocketConnections}</span>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <Radio className="h-4 w-4 text-blue-400" />
            Providers
          </h2>
          <div className="space-y-3 text-sm text-slate-300">
            {Object.entries(systemHealth.providers).map(([provider, configured]) => (
              <div key={provider} className="flex items-center justify-between capitalize">
                <span>{provider}</span>
                <span className={configured ? 'text-green-300' : 'text-slate-500'}>
                  {configured ? 'Configured' : 'Missing key'}
                </span>
              </div>
            ))}
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <AlertTriangle className="h-4 w-4 text-yellow-400" />
            Current Signals
          </h2>
          <div className="space-y-3 text-sm text-slate-300">
            <div className="flex items-center justify-between">
              <span>Pending HITL</span>
              <span>{globalMetrics.pendingHitl}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Audit events</span>
              <span>{auditEvents.length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Recent activity</span>
              <span>{activityFeed.length}</span>
            </div>
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard className="mt-6 p-4">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
          <Activity className="h-4 w-4 text-blue-400" />
          Latest Events
        </h2>
        <div className="space-y-3">
          {auditEvents.slice(0, 12).map((event) => (
            <div key={event.id} className="rounded-xl border border-slate-700/40 bg-slate-900/50 p-3">
              <div className="mb-1 flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-white">{event.employeeName}</span>
                <span className="text-xs text-slate-500">{event.timestamp.toLocaleString()}</span>
              </div>
              <div className="text-xs uppercase tracking-wide text-slate-500">{event.eventType}</div>
              <div className="mt-1 text-sm text-slate-300">{event.action}</div>
            </div>
          ))}
        </div>
      </SurfaceCard>
    </div>
  );
}
