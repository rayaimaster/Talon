import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Users, RefreshCw, Brain, Wrench,
  ClipboardList, BarChart2, Settings, Network, Shield
} from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/employees', icon: Users, label: 'Digital Employees' },
  { to: '/react-loop', icon: RefreshCw, label: 'ReAct Loop' },
  { to: '/memory', icon: Brain, label: 'Memory Explorer' },
  { to: '/tools', icon: Wrench, label: 'Tool Framework' },
  { to: '/audit', icon: ClipboardList, label: 'Audit Trail' },
  { to: '/observability', icon: BarChart2, label: 'Observability' },
  { to: '/control', icon: Settings, label: 'Control Plane' },
  { to: '/orchestration', icon: Network, label: 'Orchestration' },
];

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-full w-16 lg:w-56 bg-slate-900 border-r border-slate-700/50 z-50 flex flex-col">
      <div className="flex items-center gap-3 px-3 lg:px-4 py-4 border-b border-slate-700/50">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0">
          <Shield className="w-4 h-4 text-white" />
        </div>
        <div className="hidden lg:block">
          <div className="text-white font-bold text-sm leading-tight">Project Talon</div>
          <div className="text-slate-400 text-xs">Admin Console</div>
        </div>
      </div>

      <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-2 lg:px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group ${
                isActive
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`
            }
          >
            <Icon className="w-5 h-5 flex-shrink-0" />
            <span className="hidden lg:block">{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="px-2 lg:px-4 py-3 border-t border-slate-700/50">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="hidden lg:block text-xs text-slate-400">Connected Admin View</span>
        </div>
      </div>
    </aside>
  );
}
