import { useState } from 'react';
import { ClipboardList, Search } from 'lucide-react';
import { AuditEvent } from '../types';
import { PageHeader, RiskBadge, SurfaceCard } from '../components/UI';
import { useApp } from '../context/AppContext';

function EventModal({ event, onClose }: { event: AuditEvent; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 p-6" onClick={(event) => event.stopPropagation()}>
        <h2 className="mb-4 text-lg font-semibold text-white">Audit Event Detail</h2>
        <div className="space-y-3 rounded-xl border border-slate-700/60 bg-slate-950/80 p-4 text-sm">
          <div className="flex justify-between gap-4">
            <span className="text-slate-500">Agent</span>
            <span className="text-slate-200">{event.employeeName}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-slate-500">Timestamp</span>
            <span className="text-slate-200">{event.timestamp.toLocaleString()}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-slate-500">Type</span>
            <span className="text-slate-200">{event.eventType}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-slate-500">Outcome</span>
            <span className="text-slate-200">{event.outcome}</span>
          </div>
          {event.userId && (
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">User</span>
              <span className="text-slate-200">{event.userId}</span>
            </div>
          )}
          {event.conversationId && (
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">Conversation</span>
              <span className="text-slate-200">{event.conversationId}</span>
            </div>
          )}
          <div>
            <div className="mb-2 text-slate-500">Action</div>
            <div className="text-slate-200">{event.action}</div>
          </div>
          <div>
            <div className="mb-2 text-slate-500">Raw details</div>
            <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-300">{event.detail}</pre>
          </div>
        </div>
        <button onClick={onClose} className="mt-4 rounded-lg bg-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-600">
          Close
        </button>
      </div>
    </div>
  );
}

export default function AuditTrail() {
  const { auditEvents } = useApp();
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('all');
  const [eventTypeFilter, setEventTypeFilter] = useState('all');
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);

  const uniqueTypes = Array.from(new Set(auditEvents.map((event) => event.eventType)));
  const filtered = auditEvents.filter((event) => {
    const haystack = `${event.employeeName} ${event.eventType} ${event.action} ${event.detail}`.toLowerCase();
    const matchesSearch = !search || haystack.includes(search.toLowerCase());
    const matchesRisk = riskFilter === 'all' || event.riskLevel === riskFilter;
    const matchesType = eventTypeFilter === 'all' || event.eventType === eventTypeFilter;
    return matchesSearch && matchesRisk && matchesType;
  });

  return (
    <div>
      <PageHeader
        title="Audit Trail"
        subtitle="Operational event log from the backend. This view reflects persisted audit records, not frontend-generated demo events."
      />

      <SurfaceCard className="mb-6 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2">
            <Search className="h-4 w-4 text-slate-500" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by event type, agent, or details"
              className="w-full bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500"
            />
          </div>
          <select
            value={riskFilter}
            onChange={(event) => setRiskFilter(event.target.value)}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none"
          >
            <option value="all">All risk levels</option>
            {(['low', 'medium', 'high', 'critical'] as const).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <select
            value={eventTypeFilter}
            onChange={(event) => setEventTypeFilter(event.target.value)}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none"
          >
            <option value="all">All event types</option>
            {uniqueTypes.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
      </SurfaceCard>

      <SurfaceCard className="overflow-hidden">
        <div className="border-b border-slate-700/50 px-4 py-3 text-sm text-slate-400">
          {filtered.length} events
        </div>
        <div className="divide-y divide-slate-700/40">
          {filtered.length === 0 && (
            <div className="p-10 text-center text-sm text-slate-500">No audit events matched your filters.</div>
          )}
          {filtered.map((event) => (
            <button
              key={event.id}
              onClick={() => setSelectedEvent(event)}
              className="flex w-full items-start gap-4 px-4 py-4 text-left transition-colors hover:bg-slate-900/60"
            >
              <div className="mt-1 rounded-lg bg-slate-900 p-2 text-slate-400">
                <ClipboardList className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-white">{event.employeeName}</span>
                  <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">{event.eventType}</span>
                  <RiskBadge level={event.riskLevel} />
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${event.outcome === 'success' ? 'bg-green-500/15 text-green-300' : event.outcome === 'pending' ? 'bg-yellow-500/15 text-yellow-300' : 'bg-red-500/15 text-red-300'}`}>
                    {event.outcome}
                  </span>
                </div>
                <div className="text-sm text-slate-200">{event.action}</div>
                <div className="mt-1 line-clamp-2 text-sm text-slate-500">{event.detail}</div>
              </div>
              <div className="text-xs text-slate-500">{event.timestamp.toLocaleString()}</div>
            </button>
          ))}
        </div>
      </SurfaceCard>

      {selectedEvent && <EventModal event={selectedEvent} onClose={() => setSelectedEvent(null)} />}
    </div>
  );
}
