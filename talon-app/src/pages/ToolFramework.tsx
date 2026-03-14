import { Boxes, MessageSquare, Wrench } from 'lucide-react';
import { PageHeader, PrototypeNotice, SurfaceCard } from '../components/UI';
import { useApp } from '../context/AppContext';

export default function ToolFramework() {
  const { employees } = useApp();

  const uniqueTools = Array.from(new Set(employees.flatMap((employee) => employee.tools))).sort();

  return (
    <div>
      <PageHeader
        title="Tool Framework"
        subtitle="This page reflects the tool configuration attached to each agent, not synthetic execution metrics."
      />

      <PrototypeNotice
        title="Runtime tool telemetry is still missing"
        description="The backend currently exposes configured tools per agent, but not live per-tool rate limits, failures, or usage graphs. Those views were removed rather than simulated."
      />

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <SurfaceCard className="p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <Boxes className="h-4 w-4 text-blue-400" />
            Tool Inventory
          </h2>
          <div className="flex flex-wrap gap-2">
            {uniqueTools.map((tool) => (
              <span key={tool} className="rounded-full border border-blue-500/20 bg-blue-500/10 px-2 py-1 text-xs text-blue-300">
                {tool}
              </span>
            ))}
            {uniqueTools.length === 0 && <p className="text-sm text-slate-500">No tools configured.</p>}
          </div>
        </SurfaceCard>

        <div className="space-y-6">
          {employees.map((employee) => (
            <SurfaceCard key={employee.id} className="p-4">
              <div className="mb-4 flex items-center gap-3">
                <div
                  className="flex h-11 w-11 items-center justify-center rounded-2xl border text-xl"
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

              <div className="mb-4">
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-white">
                  <Wrench className="h-4 w-4 text-blue-400" />
                  Configured Tools
                </div>
                <div className="flex flex-wrap gap-2">
                  {employee.tools.map((tool) => (
                    <span key={tool} className="rounded-full border border-blue-500/20 bg-blue-500/10 px-2 py-1 text-xs text-blue-300">
                      {tool}
                    </span>
                  ))}
                  {employee.tools.length === 0 && <span className="text-sm text-slate-500">No tools assigned.</span>}
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-white">
                  <MessageSquare className="h-4 w-4 text-green-400" />
                  Delivery Channels
                </div>
                <div className="flex flex-wrap gap-2">
                  {employee.channels.map((channel) => (
                    <span key={channel} className="rounded-full border border-green-500/20 bg-green-500/10 px-2 py-1 text-xs text-green-300">
                      {channel}
                    </span>
                  ))}
                  {employee.channels.length === 0 && <span className="text-sm text-slate-500">No channels assigned.</span>}
                </div>
              </div>
            </SurfaceCard>
          ))}
        </div>
      </div>
    </div>
  );
}
