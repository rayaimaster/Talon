import { ReactState } from '../types';

interface ReactLoopVizProps {
  employeeId: string;
  reactState: ReactState;
  currentTask: string;
  color: string;
  compact?: boolean;
}

const STATES: { id: ReactState; label: string; desc: string }[] = [
  { id: 'perceive', label: 'Perceive', desc: 'Reading messages, alerts, and events from channels' },
  { id: 'plan', label: 'Plan', desc: 'Analyzing context, retrieving memory, forming action plan' },
  { id: 'act', label: 'Act', desc: 'Executing tools, running commands, calling APIs' },
  { id: 'observe', label: 'Observe', desc: 'Processing tool results and environment feedback' },
  { id: 'decide', label: 'Decide', desc: 'Evaluating outcomes, deciding next step or completion' },
];

export default function ReactLoopViz({ reactState, currentTask, color, compact }: ReactLoopVizProps) {
  const activeIdx = STATES.findIndex(s => s.id === reactState);
  const activeState = STATES[activeIdx];

  return (
    <div className="bg-slate-900/50 border border-slate-700/50 rounded-xl p-4">
      {!compact && (
        <div className="text-xs text-slate-400 mb-4 bg-slate-800/50 rounded-lg p-3 border border-slate-700/30">
          <span className="text-slate-500">Current: </span>
          <span className="text-slate-200">{currentTask}</span>
        </div>
      )}

      {/* State nodes in a row */}
      <div className="flex items-center justify-between gap-1 mb-4">
        {STATES.map((state, idx) => {
          const isActive = state.id === reactState;
          const isPast = idx < activeIdx;
          return (
            <div key={state.id} className="flex items-center flex-1">
              <div className={`flex flex-col items-center flex-1 ${!compact ? 'gap-2' : 'gap-1'}`}>
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all duration-500 ${
                    isActive
                      ? 'text-white shadow-lg scale-110'
                      : isPast
                      ? 'text-slate-400 border-slate-600 bg-slate-700/50'
                      : 'text-slate-600 border-slate-700 bg-slate-800/50'
                  }`}
                  style={isActive ? { borderColor: color, backgroundColor: `${color}30`, boxShadow: `0 0 12px ${color}60` } : {}}
                >
                  {idx + 1}
                </div>
                <div className={`text-xs text-center font-medium ${isActive ? 'text-white' : 'text-slate-500'}`}>
                  {state.label}
                </div>
              </div>
              {idx < STATES.length - 1 && (
                <div
                  className="w-4 h-0.5 transition-all duration-500 flex-shrink-0"
                  style={{ backgroundColor: idx < activeIdx ? color : '#334155' }}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Active state detail */}
      {activeState && (
        <div
          className="rounded-lg p-3 border transition-all duration-500"
          style={{ backgroundColor: `${color}10`, borderColor: `${color}30` }}
        >
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: color }} />
            <span className="text-xs font-semibold" style={{ color }}>
              {activeState.label.toUpperCase()}
            </span>
          </div>
          <p className="text-xs text-slate-300">{activeState.desc}</p>
        </div>
      )}
    </div>
  );
}
