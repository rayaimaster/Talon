import { ReactNode } from 'react';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  change?: string;
  changePositive?: boolean;
  icon: ReactNode;
  color?: string;
}

export function MetricCard({ title, value, subtitle, change, changePositive, icon, color = 'blue' }: MetricCardProps) {
  const colorMap: Record<string, string> = {
    blue: 'from-blue-500/10 to-blue-600/5 border-blue-500/20',
    green: 'from-green-500/10 to-green-600/5 border-green-500/20',
    purple: 'from-purple-500/10 to-purple-600/5 border-purple-500/20',
    orange: 'from-orange-500/10 to-orange-600/5 border-orange-500/20',
    yellow: 'from-yellow-500/10 to-yellow-600/5 border-yellow-500/20',
    red: 'from-red-500/10 to-red-600/5 border-red-500/20',
  };

  const iconColorMap: Record<string, string> = {
    blue: 'text-blue-400',
    green: 'text-green-400',
    purple: 'text-purple-400',
    orange: 'text-orange-400',
    yellow: 'text-yellow-400',
    red: 'text-red-400',
  };

  return (
    <div className={`bg-gradient-to-br ${colorMap[color]} border rounded-xl p-4 flex flex-col gap-3`}>
      <div className="flex items-start justify-between">
        <p className="text-slate-400 text-xs font-medium uppercase tracking-wider">{title}</p>
        <span className={`${iconColorMap[color]}`}>{icon}</span>
      </div>
      <div>
        <div className="text-2xl font-bold text-white">{value}</div>
        {subtitle && <div className="text-slate-400 text-xs mt-1">{subtitle}</div>}
      </div>
      {change && (
        <div className={`text-xs font-medium ${changePositive ? 'text-green-400' : 'text-red-400'}`}>
          {changePositive ? '↑' : '↓'} {change}
        </div>
      )}
    </div>
  );
}

interface StatusBadgeProps {
  status: 'active' | 'idle' | 'paused' | 'error';
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const map = {
    active: 'bg-green-500/20 text-green-400 border-green-500/30',
    idle: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    paused: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
    error: 'bg-red-500/20 text-red-400 border-red-500/30',
  };
  const dots = {
    active: 'bg-green-400 animate-pulse',
    idle: 'bg-yellow-400',
    paused: 'bg-slate-400',
    error: 'bg-red-400 animate-pulse',
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${map[status]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dots[status]}`} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

interface RiskBadgeProps {
  level: 'low' | 'medium' | 'high' | 'critical';
}

export function RiskBadge({ level }: RiskBadgeProps) {
  const map = {
    low: 'bg-green-500/20 text-green-400 border-green-500/30',
    medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    critical: 'bg-red-500/20 text-red-400 border-red-500/30',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${map[level]}`}>
      {level.toUpperCase()}
    </span>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-white">{title}</h1>
      {subtitle && <p className="text-slate-400 mt-1 text-sm">{subtitle}</p>}
    </div>
  );
}

export function SurfaceCard({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-slate-700/50 bg-slate-800/50 ${className}`}>
      {children}
    </div>
  );
}

export function PrototypeNotice({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/10 p-4">
      <div className="text-sm font-semibold text-yellow-300">{title}</div>
      <p className="mt-1 text-sm text-slate-300">{description}</p>
    </div>
  );
}
