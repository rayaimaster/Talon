import { useEffect, useState } from 'react';
import { MessageSquare, RefreshCw } from 'lucide-react';
import { PageHeader, PrototypeNotice, SurfaceCard } from '../components/UI';
import { useApp } from '../context/AppContext';
import { HistoryMessage } from '../types';

export default function ReActLoop() {
  const { employees, selectedEmployeeId, selectEmployee, loadEmployeeHistory } = useApp();
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  const selectedEmployee = employees.find((employee) => employee.id === selectedEmployeeId) ?? employees[0];

  useEffect(() => {
    if (!selectedEmployee) {
      return;
    }

    let cancelled = false;

    async function loadHistory() {
      try {
        const result = await loadEmployeeHistory(selectedEmployee.id, 20);
        if (!cancelled) {
          setHistory(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setHistory([]);
          setError(err instanceof Error ? err.message : 'Failed to load history');
        }
      }
    }

    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, [selectedEmployee?.id, loadEmployeeHistory]);

  return (
    <div>
      <PageHeader
        title="ReAct Loop"
        subtitle="The backend does not stream internal reasoning state yet, so this page focuses on the real history it does expose."
      />

      <PrototypeNotice
        title="Internal loop phases are not available yet"
        description="The original animated loop visualizer was mock-only. This version shows recent conversation history for the selected agent until the backend exposes live planning and tool-state telemetry."
      />

      <div className="mt-6 flex flex-wrap gap-2">
        {employees.map((employee) => (
          <button
            key={employee.id}
            onClick={() => selectEmployee(employee.id)}
            className={`rounded-xl border px-3 py-2 text-sm font-medium transition-colors ${selectedEmployee?.id === employee.id ? 'border-blue-500/50 bg-blue-500/10 text-white' : 'border-slate-700 bg-slate-900 text-slate-400 hover:text-white'}`}
          >
            {employee.emoji} {employee.name}
          </button>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        {selectedEmployee && (
          <SurfaceCard className="p-4">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
              <RefreshCw className="h-4 w-4 text-blue-400" />
              Current Agent Snapshot
            </h2>
            <div className="space-y-3 text-sm text-slate-300">
              <div className="flex items-center justify-between">
                <span>Name</span>
                <span className="text-white">{selectedEmployee.name}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Status</span>
                <span className="text-white">{selectedEmployee.status}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Provider</span>
                <span className="text-white capitalize">{selectedEmployee.provider}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Messages</span>
                <span className="text-white">{selectedEmployee.stats.messages}</span>
              </div>
              <div className="pt-2 text-slate-400">{selectedEmployee.currentTask}</div>
            </div>
          </SurfaceCard>
        )}

        <SurfaceCard className="p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <MessageSquare className="h-4 w-4 text-green-400" />
            Recent History
          </h2>
          {error && <p className="mb-3 text-sm text-red-400">{error}</p>}
          <div className="space-y-3">
            {history.length === 0 && !error && <p className="text-sm text-slate-500">No history available yet.</p>}
            {history.map((message) => (
              <div key={message.id} className="rounded-xl border border-slate-700/40 bg-slate-900/50 p-3">
                <div className="mb-1 flex items-center justify-between gap-3">
                  <span className="text-xs uppercase tracking-wide text-slate-500">{message.role}</span>
                  <span className="text-xs text-slate-500">{message.timestamp.toLocaleString()}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm text-slate-300">{message.content}</p>
              </div>
            ))}
          </div>
        </SurfaceCard>
      </div>
    </div>
  );
}
