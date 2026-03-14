// API and WebSocket configuration
// Priority: localStorage (user-configured) → env var → localhost default

const STORAGE_KEY = 'talon_backend_url';

export function getBackendUrl(): string {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) return stored.replace(/\/$/, '');
  return (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
}

export function setBackendUrl(url: string) {
  localStorage.setItem(STORAGE_KEY, url.replace(/\/$/, ''));
}

export function clearBackendUrl() {
  localStorage.removeItem(STORAGE_KEY);
}

export function getWsUrl(): string {
  const apiUrl = getBackendUrl();
  // Convert http(s):// to ws(s)://
  return apiUrl.replace(/^http/, 'ws');
}

export function getEndpoints() {
  const API_URL = getBackendUrl();
  const WS_URL = getWsUrl();
  return {
    agents: `${API_URL}/api/agents`,
    agent: (id: string) => `${API_URL}/api/agents/${id}`,
    chatHistory: (agentId: string, sessionId: string) =>
      `${API_URL}/api/chat/${agentId}/history/${sessionId}`,
    wsChat: (agentId: string, sessionId: string) =>
      `${WS_URL}/ws/chat/${agentId}/${sessionId}`,
  };
}

// Legacy compat exports (will be dynamic now)
export const API_URL = getBackendUrl();
export const WS_URL = getWsUrl();
export const endpoints = getEndpoints();
