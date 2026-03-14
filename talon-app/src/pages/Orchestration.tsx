import { GitBranch, MessageSquare, Network } from 'lucide-react';
import { PageHeader, PrototypeNotice, SurfaceCard } from '../components/UI';
import { useApp } from '../context/AppContext';

export default function Orchestration() {
  const { employees } = useApp();

  return (
    <div>
      <PageHeader
        title="Orchestration"
        subtitle="Current backend orchestration is configuration-driven; the dashboard no longer simulates delegation graphs that do not exist in the API."
      />

      <PrototypeNotice
        title="Delegation telemetry is still a roadmap item"
        description="The backend can route work to different agents, but it does not yet expose live supervisor-worker chains, delegation traces, or checkpoint graphs for the UI to render."
      />

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <SurfaceCard className="p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <Network className="h-4 w-4 text-blue-400" />
            Registered Agents
          </h2>
          <div className="space-y-3">
            {employees.map((employee) => (
              <div key={employee.id} className="rounded-xl border border-slate-700/40 bg-slate-900/50 p-4">
                <div className="mb-2 flex items-center gap-3">
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
                <div className="text-sm text-slate-400">{employee.currentTask}</div>
              </div>
            ))}
          </div>
        </SurfaceCard>

        <div className="space-y-6">
          <SurfaceCard className="p-4">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
              <MessageSquare className="h-4 w-4 text-green-400" />
              Channel Topology
            </h2>
            <div className="space-y-3">
              {employees.map((employee) => (
                <div key={employee.id} className="rounded-xl border border-slate-700/40 bg-slate-900/50 p-4">
                  <div className="mb-2 text-sm font-semibold text-white">{employee.name}</div>
                  <div className="flex flex-wrap gap-2">
                    {employee.channels.map((channel) => (
                      <span key={channel} className="rounded-full border border-green-500/20 bg-green-500/10 px-2 py-1 text-xs text-green-300">
                        {channel}
                      </span>
                    ))}
                    {employee.channels.length === 0 && <span className="text-sm text-slate-500">No channels assigned.</span>}
                  </div>
                </div>
              ))}
            </div>
          </SurfaceCard>

          <SurfaceCard className="p-4">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
              <GitBranch className="h-4 w-4 text-purple-400" />
              Next Backend Work
            </h2>
            <ul className="space-y-2 text-sm text-slate-300">
              <li>Expose delegation events from the ReAct loop as first-class audit records.</li>
              <li>Add orchestration APIs for parent/child task relationships.</li>
              <li>Persist checkpoint IDs if rollback and recovery become supported features.</li>
            </ul>
          </SurfaceCard>
        </div>
      </div>
    </div>
  );
}
