import { ConnectionStatus } from '../types';

interface ConnectionBadgeProps {
  status: ConnectionStatus;
}

const labels: Record<ConnectionStatus, string> = {
  connected: 'Connected',
  connecting: 'Connecting...',
  disconnected: 'Disconnected',
  error: 'Connection Error',
};

const colors: Record<ConnectionStatus, string> = {
  connected: 'bg-green-400',
  connecting: 'bg-yellow-400 animate-pulse',
  disconnected: 'bg-gray-500',
  error: 'bg-red-400',
};

const textColors: Record<ConnectionStatus, string> = {
  connected: 'text-green-400',
  connecting: 'text-yellow-400',
  disconnected: 'text-gray-400',
  error: 'text-red-400',
};

export function ConnectionBadge({ status }: ConnectionBadgeProps) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full ${colors[status]}`} />
      <span className={`text-xs font-medium ${textColors[status]}`}>
        {labels[status]}
      </span>
    </div>
  );
}
