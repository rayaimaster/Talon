import { useEffect, useState } from 'react';
import { Brain, Database, Search } from 'lucide-react';
import { PageHeader, SurfaceCard } from '../components/UI';
import { useApp } from '../context/AppContext';
import { EmployeeMemory, MemoryEntry } from '../types';

function MemorySection({ title, entries }: { title: string; entries: MemoryEntry[] }) {
  return (
    <SurfaceCard className="p-4">
      <h2 className="mb-4 text-sm font-semibold text-white">{title}</h2>
      <div className="space-y-3">
        {entries.length === 0 && <p className="text-sm text-slate-500">No entries found.</p>}
        {entries.map((entry) => (
          <div key={entry.id} className="rounded-xl border border-slate-700/40 bg-slate-900/50 p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="text-sm font-medium text-white">{entry.title}</div>
              {entry.timestamp && <div className="text-xs text-slate-500">{entry.timestamp.toLocaleString()}</div>}
            </div>
            <pre className="whitespace-pre-wrap text-sm text-slate-300">{entry.content}</pre>
            <div className="mt-3 flex flex-wrap gap-2">
              {entry.tags.map((tag) => (
                <span key={tag} className="rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                  #{tag}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </SurfaceCard>
  );
}

export default function MemoryExplorer() {
  const { employees, selectedEmployeeId, selectEmployee, loadEmployeeMemory } = useApp();
  const [memory, setMemory] = useState<EmployeeMemory>({ episodicMemories: [], entityMemories: [] });
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);

  const selectedEmployee = employees.find((employee) => employee.id === selectedEmployeeId) ?? employees[0];

  useEffect(() => {
    if (!selectedEmployee) {
      return;
    }

    let cancelled = false;

    async function refresh() {
      try {
        const result = await loadEmployeeMemory(selectedEmployee.id, 50);
        if (!cancelled) {
          setMemory(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load memory');
        }
      }
    }

    void refresh();
    return () => {
      cancelled = true;
    };
  }, [selectedEmployee?.id, loadEmployeeMemory]);

  const query = search.trim().toLowerCase();
  const episodic = memory.episodicMemories.filter((entry) => {
    if (!query) {
      return true;
    }
    return `${entry.title} ${entry.content} ${entry.tags.join(' ')}`.toLowerCase().includes(query);
  });
  const entities = memory.entityMemories.filter((entry) => {
    if (!query) {
      return true;
    }
    return `${entry.title} ${entry.content} ${entry.tags.join(' ')}`.toLowerCase().includes(query);
  });

  return (
    <div>
      <PageHeader
        title="Memory Explorer"
        subtitle="Read the real episodic and entity memory persisted for each agent in SQLite."
      />

      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="flex flex-wrap gap-2">
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
        <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2">
          <Search className="h-4 w-4 text-slate-500" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search summaries, entities, or facts"
            className="w-full bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500"
          />
        </div>
      </div>

      {selectedEmployee && (
        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
          <SurfaceCard className="p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Brain className="h-4 w-4 text-purple-400" />
              Episodic Entries
            </div>
            <div className="mt-3 text-2xl font-bold text-white">{selectedEmployee.stats.episodicMemories}</div>
          </SurfaceCard>
          <SurfaceCard className="p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Database className="h-4 w-4 text-blue-400" />
              Entity Records
            </div>
            <div className="mt-3 text-2xl font-bold text-white">{selectedEmployee.stats.entityRecords}</div>
          </SurfaceCard>
          <SurfaceCard className="p-4">
            <div className="text-sm font-semibold text-white">Agent Context</div>
            <div className="mt-3 text-sm text-slate-300">{selectedEmployee.currentTask}</div>
          </SurfaceCard>
        </div>
      )}

      {error && <div className="mb-4 text-sm text-red-400">{error}</div>}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <MemorySection title="Episodic Memory" entries={episodic} />
        <MemorySection title="Entity Memory" entries={entities} />
      </div>
    </div>
  );
}
