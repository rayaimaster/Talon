import { useNavigate } from 'react-router-dom';
import { useAgents } from '../hooks/useAgents';
import { AgentCard } from '../components/AgentCard';
import { Zap, RefreshCw, Unplug } from 'lucide-react';
import { getBackendUrl } from '../config';

export function AgentSelectPage({ onDisconnect }: { onDisconnect?: () => void }) {
  const navigate = useNavigate();
  const { agents, loading, error, refetch } = useAgents();

  return (
    <div className="min-h-screen bg-gray-900 text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-700/50 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center shadow-lg">
              <Zap size={18} className="text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white leading-none">Project Talon</h1>
              <p className="text-xs text-gray-400 leading-none mt-0.5">Digital Employee Platform</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800/60 border border-gray-700/50">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-xs text-gray-400">
                {agents.filter(a => a.status === 'active').length} online
              </span>
            </div>
            <div className="text-xs text-gray-600 hidden sm:block font-mono bg-gray-800/40 px-2 py-1 rounded">
              {getBackendUrl()}
            </div>
            <button
              onClick={refetch}
              className="p-2 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-700/50 transition-colors"
              title="Refresh agents"
            >
              <RefreshCw size={14} />
            </button>
            {onDisconnect && (
              <button
                onClick={onDisconnect}
                className="p-2 rounded-lg text-gray-500 hover:text-red-400 hover:bg-gray-700/50 transition-colors"
                title="Change backend URL"
              >
                <Unplug size={14} />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-10">
        <div className="mb-8">
          <h2 className="text-3xl font-bold text-white mb-2">
            Chat with a Digital Employee
          </h2>
          <p className="text-gray-400 text-lg">
            Select an agent to start a real-time conversation powered by AI.
          </p>
        </div>

        {/* Loading */}
        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {[1, 2, 3].map(i => (
              <div
                key={i}
                className="h-52 rounded-2xl bg-gray-800/40 border border-gray-700/30 animate-pulse"
              />
            ))}
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="text-4xl mb-4">⚠️</div>
            <h3 className="text-lg font-semibold text-white mb-2">Failed to load agents</h3>
            <p className="text-gray-400 text-sm mb-2 max-w-sm">
              Could not connect to the Talon backend at:
            </p>
            <p className="text-xs text-blue-400 font-mono mb-4 bg-gray-800/60 px-4 py-2 rounded-lg">
              {getBackendUrl()}
            </p>
            <p className="text-xs text-gray-500 mb-6 max-w-xs">
              Make sure the backend is running and accessible from your browser.
            </p>
            <div className="flex gap-3">
              <button
                onClick={refetch}
                className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-500 transition-colors"
              >
                Try again
              </button>
              {onDisconnect && (
                <button
                  onClick={onDisconnect}
                  className="px-4 py-2 rounded-lg bg-gray-700 text-gray-300 text-sm font-medium hover:bg-gray-600 transition-colors"
                >
                  Change URL
                </button>
              )}
            </div>
          </div>
        )}

        {/* Agent grid */}
        {!loading && !error && (
          <>
            {agents.length === 0 ? (
              <div className="text-center py-20 text-gray-500">
                No agents configured. Check your agents.yaml file.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {agents.map(agent => (
                  <AgentCard
                    key={agent.id}
                    agent={agent}
                    onClick={() => navigate(`/chat/${agent.id}`)}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {/* Info footer */}
        <div className="mt-16 pt-8 border-t border-gray-700/30">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-center">
            {[
              { icon: '⚡', title: 'Real-time', desc: 'WebSocket-powered live responses' },
              { icon: '🔧', title: 'Tool-equipped', desc: 'Agents use real tools to answer questions' },
              { icon: '🧠', title: 'Memory', desc: 'Conversations persist across sessions' },
            ].map(item => (
              <div key={item.title} className="flex flex-col items-center gap-2">
                <div className="text-2xl">{item.icon}</div>
                <div className="text-sm font-semibold text-gray-300">{item.title}</div>
                <div className="text-xs text-gray-500">{item.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
