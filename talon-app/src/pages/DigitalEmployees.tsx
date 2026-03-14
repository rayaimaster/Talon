import { useEffect, useState } from 'react';
import { MessageSquare, Pause, Play, Settings2, Wrench } from 'lucide-react';
import { PageHeader, PrototypeNotice, StatusBadge, SurfaceCard } from '../components/UI';
import { useApp } from '../context/AppContext';
import { DigitalEmployee, HistoryMessage } from '../types';

function EmployeeDetail({ employee }: { employee: DigitalEmployee }) {
  const { pauseEmployee, resumeEmployee, loadEmployeeHistory, isLoading } = useApp();
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadHistory() {
      try {
        const result = await loadEmployeeHistory(employee.id, 12);
        if (!cancelled) {
          setHistory(result);
          setHistoryError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setHistory([]);
          setHistoryError(error instanceof Error ? error.message : 'Failed to load history');
        }
      }
    }

    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, [employee.id, loadEmployeeHistory]);

  return (
    <div className="space-y-4">
      <SurfaceCard className="p-5">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div
              className="flex h-14 w-14 items-center justify-center rounded-2xl border text-2xl"
              style={{ borderColor: `${employee.color}50`, backgroundColor: `${employee.color}18` }}
            >
              {employee.emoji}
            </div>
            <div>
              <div className="text-xl font-bold text-white">{employee.name}</div>
              <div className="text-sm font-medium" style={{ color: employee.color }}>
                {employee.role}
              </div>
            </div>
          </div>
          <StatusBadge status={employee.status} />
        </div>

        <p className="mb-4 text-sm text-slate-400">{employee.currentTask}</p>

        <div className="mb-4 flex flex-wrap gap-2">
          <button
            onClick={() => void (employee.status === 'active' ? pauseEmployee(employee.id) : resumeEmployee(employee.id))}
            disabled={isLoading}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-60"
          >
            {employee.status === 'active' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {employee.status === 'active' ? 'Pause agent' : 'Resume agent'}
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div className="rounded-xl bg-slate-900/70 p-3">
            <div className="text-xs text-slate-500">Provider</div>
            <div className="mt-1 text-sm font-semibold text-white capitalize">{employee.provider}</div>
          </div>
          <div className="rounded-xl bg-slate-900/70 p-3">
            <div className="text-xs text-slate-500">Messages</div>
            <div className="mt-1 text-sm font-semibold text-white">{employee.stats.messages}</div>
          </div>
          <div className="rounded-xl bg-slate-900/70 p-3">
            <div className="text-xs text-slate-500">Episodic</div>
            <div className="mt-1 text-sm font-semibold text-white">{employee.stats.episodicMemories}</div>
          </div>
          <div className="rounded-xl bg-slate-900/70 p-3">
            <div className="text-xs text-slate-500">Entities</div>
            <div className="mt-1 text-sm font-semibold text-white">{employee.stats.entityRecords}</div>
          </div>
        </div>
      </SurfaceCard>

      <SurfaceCard className="p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
          <Wrench className="h-4 w-4 text-blue-400" />
          Tools and Channels
        </h2>
        <div className="mb-3 flex flex-wrap gap-2">
          {employee.tools.map((tool) => (
            <span key={tool} className="rounded-full border border-blue-500/20 bg-blue-500/10 px-2 py-1 text-xs text-blue-300">
              {tool}
            </span>
          ))}
          {employee.tools.length === 0 && <span className="text-sm text-slate-500">No tools configured.</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          {employee.channels.map((channel) => (
            <span key={channel} className="rounded-full border border-green-500/20 bg-green-500/10 px-2 py-1 text-xs text-green-300">
              {channel}
            </span>
          ))}
          {employee.channels.length === 0 && <span className="text-sm text-slate-500">No channels configured.</span>}
        </div>
      </SurfaceCard>

      <SurfaceCard className="p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
          <MessageSquare className="h-4 w-4 text-green-400" />
          Recent Conversation History
        </h2>
        {historyError && <p className="text-sm text-red-400">{historyError}</p>}
        {!historyError && history.length === 0 && <p className="text-sm text-slate-400">No conversation history yet.</p>}
        <div className="space-y-3">
          {history.map((message) => (
            <div key={message.id} className="rounded-xl border border-slate-700/40 bg-slate-900/50 p-3">
              <div className="mb-1 flex items-center justify-between gap-3">
                <span className="text-xs uppercase tracking-wide text-slate-500">{message.role}</span>
                <span className="text-xs text-slate-500">{message.timestamp.toLocaleString()}</span>
              </div>
              <p className="text-sm text-slate-300 whitespace-pre-wrap">{message.content}</p>
              <div className="mt-2 text-xs text-slate-500">Conversation: {message.conversationId}</div>
            </div>
          ))}
        </div>
      </SurfaceCard>
    </div>
  );
}

export default function DigitalEmployees() {
  const { employees, selectedEmployeeId, selectEmployee } = useApp();
  const [filter, setFilter] = useState<'all' | 'active' | 'paused'>('all');

  const filtered = employees.filter((employee) => filter === 'all' || employee.status === filter);
  const selected = employees.find((employee) => employee.id === selectedEmployeeId) ?? filtered[0];

  useEffect(() => {
    if (!selectedEmployeeId && filtered[0]) {
      selectEmployee(filtered[0].id);
    }
  }, [filtered, selectedEmployeeId, selectEmployee]);

  return (
    <div>
      <PageHeader
        title="Digital Employees"
        subtitle="Live agent inventory with real pause and resume controls backed by the Talon API."
      />

      <PrototypeNotice
        title="Operator modes are intentionally narrow"
        description="Pause and resume are real backend actions. Read-only, supervised, and kill controls were removed from this screen until the backend supports them as real operating modes."
      />

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <SurfaceCard className="p-4">
          <div className="mb-4 flex items-center gap-2">
            {(['all', 'active', 'paused'] as const).map((value) => (
              <button
                key={value}
                onClick={() => setFilter(value)}
                className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${filter === value ? 'bg-blue-600 text-white' : 'bg-slate-900 text-slate-400 hover:text-white'}`}
              >
                {value.charAt(0).toUpperCase() + value.slice(1)}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            {filtered.map((employee) => (
              <button
                key={employee.id}
                onClick={() => selectEmployee(employee.id)}
                className={`w-full rounded-xl border p-4 text-left transition-colors ${selected?.id === employee.id ? 'border-blue-500/50 bg-blue-500/10' : 'border-slate-700/50 bg-slate-900/50 hover:border-slate-600'}`}
              >
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className="flex h-10 w-10 items-center justify-center rounded-2xl border text-lg"
                      style={{ borderColor: `${employee.color}50`, backgroundColor: `${employee.color}18` }}
                    >
                      {employee.emoji}
                    </div>
                    <div>
                      <div className="font-semibold text-white">{employee.name}</div>
                      <div className="text-xs" style={{ color: employee.color }}>
                        {employee.role}
                      </div>
                    </div>
                  </div>
                  <StatusBadge status={employee.status} />
                </div>
                <div className="text-sm text-slate-400">{employee.currentTask}</div>
              </button>
            ))}
          </div>
        </SurfaceCard>

        {selected ? (
          <EmployeeDetail employee={selected} />
        ) : (
          <SurfaceCard className="flex items-center justify-center p-12">
            <div className="text-center text-slate-400">
              <Settings2 className="mx-auto mb-3 h-8 w-8 text-slate-600" />
              Select an employee to view details.
            </div>
          </SurfaceCard>
        )}
      </div>
    </div>
  );
}
