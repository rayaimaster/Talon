import { useEffect, useRef, useCallback, useState } from 'react';
import { ConnectionStatus, WsMessage } from '../types';
import { getEndpoints } from '../config';

interface UseWebSocketOptions {
  agentId: string;
  sessionId: string;
  onMessage: (msg: WsMessage) => void;
  onStatusChange: (status: ConnectionStatus) => void;
}

const MAX_RECONNECT_DELAY = 30000;
const BASE_RECONNECT_DELAY = 1000;

export function useWebSocket({
  agentId,
  sessionId,
  onMessage,
  onStatusChange,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isUnmountedRef = useRef(false);
  const onMessageRef = useRef(onMessage);
  const onStatusChangeRef = useRef(onStatusChange);

  // Keep refs up to date without re-connecting
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);
  useEffect(() => { onStatusChangeRef.current = onStatusChange; }, [onStatusChange]);

  const connect = useCallback(() => {
    if (isUnmountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    onStatusChangeRef.current('connecting');
    const url = getEndpoints().wsChat(agentId, sessionId);

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isUnmountedRef.current) { ws.close(); return; }
        reconnectAttemptRef.current = 0;
        onStatusChangeRef.current('connected');
      };

      ws.onmessage = (event) => {
        if (isUnmountedRef.current) return;
        try {
          const data: WsMessage = JSON.parse(event.data);
          onMessageRef.current(data);
        } catch {
          console.error('WS parse error:', event.data);
        }
      };

      ws.onclose = (event) => {
        if (isUnmountedRef.current) return;
        onStatusChangeRef.current('disconnected');
        wsRef.current = null;

        // Don't reconnect if closed intentionally (code 1000 or 4xxx)
        if (event.code === 1000 || event.code >= 4000) return;

        // Exponential backoff reconnect
        const delay = Math.min(
          BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttemptRef.current),
          MAX_RECONNECT_DELAY,
        );
        reconnectAttemptRef.current++;
        onStatusChangeRef.current('connecting');
        reconnectTimerRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        if (isUnmountedRef.current) return;
        onStatusChangeRef.current('error');
      };
    } catch (err) {
      console.error('WS connect error:', err);
      onStatusChangeRef.current('error');
    }
  }, [agentId, sessionId]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'Intentional disconnect');
      wsRef.current = null;
    }
  }, []);

  const sendMessage = useCallback((text: string, user: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'message', text, user }));
      return true;
    }
    return false;
  }, []);

  useEffect(() => {
    isUnmountedRef.current = false;
    connect();
    return () => {
      isUnmountedRef.current = true;
      disconnect();
    };
  }, [connect, disconnect]);

  return { sendMessage, disconnect, reconnect: connect };
}
