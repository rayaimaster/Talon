import { useNavigate, useLocation } from 'react-router-dom';
import { AgentCard } from './AgentCard';
import { Agent } from '../types';
import { Zap } from 'lucide-react';

interface SidebarProps {
  agents: Agent[];
  currentAgentId?: string;
}

export function Sidebar({ agents, currentAgentId }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="w-56 flex-shrink-0 bg-gray-900/80 border-r border-gray-700/50 flex flex-col h-full">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-gray-700/50">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 hover:opacity-80 transition-opacity"
        >
          <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center">
            <Zap size={14} className="text-white" />
          </div>
          <div>
            <div className="text-sm font-bold text-white leading-none">Talon</div>
            <div className="text-xs text-gray-500 leading-none mt-0.5">Digital Employees</div>
          </div>
        </button>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto py-2 px-2">
        <div className="text-xs font-medium text-gray-600 uppercase tracking-wider px-2 mb-2">
          Agents
        </div>
        <div className="space-y-0.5">
          {agents.map(agent => (
            <AgentCard
              key={agent.id}
              agent={agent}
              compact
              active={currentAgentId === agent.id}
              onClick={() => navigate(`/chat/${agent.id}`)}
            />
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-700/50">
        <div className="text-xs text-gray-600">Project Talon v2</div>
      </div>
    </div>
  );
}
