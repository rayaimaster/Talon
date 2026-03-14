import { Agent } from '../types';

interface AgentCardProps {
  agent: Agent;
  onClick: () => void;
  compact?: boolean;
  active?: boolean;
}

export function AgentCard({ agent, onClick, compact = false, active = false }: AgentCardProps) {
  const isOnline = agent.status === 'active';

  if (compact) {
    return (
      <button
        onClick={onClick}
        className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-all text-left ${
          active
            ? 'bg-white/10 text-white'
            : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
        }`}
      >
        <div className="relative flex-shrink-0">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold"
            style={{ backgroundColor: agent.color + '33', border: `1px solid ${agent.color}55` }}
          >
            {agent.emoji}
          </div>
          <div
            className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-gray-900 ${
              isOnline ? 'bg-green-400' : 'bg-gray-500'
            }`}
          />
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-medium text-sm truncate">{agent.name}</div>
          <div className="text-xs text-gray-500 truncate">{agent.role}</div>
        </div>
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      className="group relative flex flex-col p-6 rounded-2xl border transition-all duration-200 text-left cursor-pointer
        bg-gray-800/60 border-gray-700/50 hover:border-opacity-80 hover:scale-[1.02] hover:shadow-2xl active:scale-100"
      style={{
        boxShadow: active ? `0 0 0 2px ${agent.color}66, 0 8px 32px ${agent.color}22` : undefined,
        borderColor: active ? agent.color + '88' : undefined,
      }}
    >
      {/* Status badge */}
      <div className="absolute top-4 right-4 flex items-center gap-1.5">
        <div
          className={`w-2 h-2 rounded-full ${isOnline ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`}
        />
        <span className={`text-xs font-medium ${isOnline ? 'text-green-400' : 'text-gray-500'}`}>
          {isOnline ? 'Online' : 'Paused'}
        </span>
      </div>

      {/* Avatar */}
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl mb-4 transition-transform group-hover:scale-110"
        style={{
          backgroundColor: agent.color + '22',
          border: `2px solid ${agent.color}44`,
        }}
      >
        {agent.emoji}
      </div>

      {/* Info */}
      <div className="mb-2">
        <h3 className="text-white font-bold text-lg leading-tight">{agent.name}</h3>
        <p className="text-sm font-medium mt-0.5" style={{ color: agent.color }}>
          {agent.role}
        </p>
      </div>

      <p className="text-gray-400 text-sm leading-relaxed line-clamp-2 flex-1">
        {agent.description || agent.role}
      </p>

      {/* Tools */}
      {agent.tools && agent.tools.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {agent.tools.slice(0, 3).map(tool => (
            <span
              key={tool}
              className="px-2 py-0.5 rounded-md text-xs font-mono bg-gray-700/60 text-gray-400"
            >
              {tool}
            </span>
          ))}
          {agent.tools.length > 3 && (
            <span className="px-2 py-0.5 rounded-md text-xs bg-gray-700/60 text-gray-500">
              +{agent.tools.length - 3}
            </span>
          )}
        </div>
      )}

      {/* Provider badge */}
      <div className="mt-3 pt-3 border-t border-gray-700/50 flex items-center gap-2">
        <span className="text-xs text-gray-500">
          {agent.provider} · {agent.model?.split('-').slice(0, 2).join('-')}
        </span>
      </div>

      {/* Hover CTA */}
      <div
        className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none flex items-end justify-center pb-5"
        style={{ background: `linear-gradient(to top, ${agent.color}18 0%, transparent 60%)` }}
      >
        <span className="text-sm font-semibold" style={{ color: agent.color }}>
          Start Chat →
        </span>
      </div>
    </button>
  );
}
