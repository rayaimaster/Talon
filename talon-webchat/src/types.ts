// Agent type definitions for Project Talon Webchat

export interface Agent {
  id: string;
  name: string;
  role: string;
  emoji: string;
  color: string;
  status: 'active' | 'paused';
  provider: string;
  model: string;
  tools: string[];
  description?: string;
}

export interface ChatMessage {
  id: string;
  type: 'message' | 'tool_call' | 'tool_result' | 'error' | 'typing';
  role?: 'user' | 'assistant';
  text?: string;
  agent?: string;
  agent_id?: string;
  tool?: string;
  input?: string;
  result?: string;
  timestamp: number;
  isExpanded?: boolean;
}

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected' | 'error';

export interface WsMessage {
  type: string;
  text?: string;
  agent?: string;
  agent_id?: string;
  tool?: string;
  input?: string;
  result?: string;
  timestamp?: number;
  session_id?: string;
  role?: string;
  emoji?: string;
  color?: string;
}
