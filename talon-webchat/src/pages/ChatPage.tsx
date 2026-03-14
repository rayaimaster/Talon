import { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { v4 as uuidv4 } from 'uuid';
import { ArrowLeft, Send, Paperclip } from 'lucide-react';

import { useWebSocket } from '../hooks/useWebSocket';
import { useAgents } from '../hooks/useAgents';
import { MessageBubble } from '../components/MessageBubble';
import { ConnectionBadge } from '../components/ConnectionBadge';
import { Sidebar } from '../components/Sidebar';
import { ChatMessage, ConnectionStatus, WsMessage } from '../types';
import { getEndpoints } from '../config';

const SESSION_KEY_PREFIX = 'talon_session_';

function getOrCreateSession(agentId: string): string {
  const key = SESSION_KEY_PREFIX + agentId;
  let session = localStorage.getItem(key);
  if (!session) {
    session = uuidv4();
    localStorage.setItem(key, session);
  }
  return session;
}

export function ChatPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const { agents } = useAgents();

  const agent = agents.find(a => a.id === agentId);
  const sessionId = agentId ? getOrCreateSession(agentId) : '';

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting');
  const [isAgentTyping, setIsAgentTyping] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setMessages([]);
    setInputText('');
    setConnectionStatus('connecting');
    setIsAgentTyping(false);
    setHistoryLoaded(false);
  }, [agentId, sessionId]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isAgentTyping]);

  // Load chat history for the active agent/session pair.
  useEffect(() => {
    if (!agentId || !sessionId || historyLoaded) return;

    const controller = new AbortController();

    fetch(getEndpoints().chatHistory(agentId, sessionId), { signal: controller.signal })
      .then(res => res.json())
      .then(data => {
        if (data.messages && data.messages.length > 0) {
          const historicMsgs: ChatMessage[] = data.messages.map((m: any, i: number) => ({
            id: `hist-${i}`,
            type: m.type || 'message',
            role: m.role === 'assistant' ? 'assistant' : 'user',
            text: m.text,
            agent: m.agent,
            agent_id: m.agent_id,
            tool: m.tool,
            input: m.input,
            timestamp: Date.now() / 1000 - (data.messages.length - i) * 60,
          }));
          setMessages(historicMsgs);
        }
        setHistoryLoaded(true);
      })
      .catch(err => {
        if (err?.name !== 'AbortError') {
          setHistoryLoaded(true);
        }
      });

    return () => controller.abort();
  }, [agentId, sessionId, historyLoaded]);

  // Show welcome message once connected and no history
  const onConnectionStatusChange = useCallback((status: ConnectionStatus) => {
    setConnectionStatus(status);
  }, []);

  const onWsMessage = useCallback((msg: WsMessage) => {
    if (msg.type === 'welcome') {
      // Only show welcome if no history
      if (!historyLoaded) {
        const welcome: ChatMessage = {
          id: uuidv4(),
          type: 'message',
          role: 'assistant',
          text: `Hi! I'm **${msg.agent}**, your ${msg.role || 'Digital Employee'}. How can I help you today?`,
          agent: msg.agent,
          agent_id: msg.agent_id,
          timestamp: Date.now() / 1000,
        };
        setMessages(prev => {
          if (prev.length === 0) return [welcome];
          return prev;
        });
      }
      return;
    }

    if (msg.type === 'typing') {
      setIsAgentTyping(true);
      return;
    }

    if (msg.type === 'pong') return;

    // Remove typing indicator for tool_call, tool_result, message, error
    setIsAgentTyping(false);

    const chatMsg: ChatMessage = {
      id: uuidv4(),
      type: msg.type as ChatMessage['type'],
      role: msg.type === 'message' ? 'assistant' : undefined,
      text: msg.text,
      agent: msg.agent,
      agent_id: msg.agent_id,
      tool: msg.tool,
      input: msg.input,
      result: msg.result,
      timestamp: msg.timestamp || Date.now() / 1000,
    };

    setMessages(prev => [...prev, chatMsg]);
  }, [historyLoaded]);

  const { sendMessage } = useWebSocket({
    agentId: agentId || '',
    sessionId,
    onMessage: onWsMessage,
    onStatusChange: onConnectionStatusChange,
  });

  const handleSend = useCallback(() => {
    const text = inputText.trim();
    if (!text) return;

    // Add user message immediately
    const userMsg: ChatMessage = {
      id: uuidv4(),
      type: 'message',
      role: 'user',
      text,
      timestamp: Date.now() / 1000,
    };
    setMessages(prev => [...prev, userMsg]);
    setInputText('');
    setIsAgentTyping(true);

    const sent = sendMessage(text, 'web-user');
    if (!sent) {
      setIsAgentTyping(false);
      const errMsg: ChatMessage = {
        id: uuidv4(),
        type: 'error',
        text: 'Not connected to server. Please wait for reconnection.',
        timestamp: Date.now() / 1000,
      };
      setMessages(prev => [...prev, errMsg]);
    }
  }, [inputText, sendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [inputText]);

  return (
    <div className="flex h-screen bg-gray-900 text-white overflow-hidden">
      {/* Sidebar */}
      <Sidebar agents={agents} currentAgentId={agentId} />

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-700/50 bg-gray-900/80 backdrop-blur-sm flex-shrink-0">
          <button
            onClick={() => navigate('/')}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700/50 transition-colors"
          >
            <ArrowLeft size={16} />
          </button>

          {agent && (
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-base flex-shrink-0"
              style={{ backgroundColor: agent.color + '22' }}
            >
              {agent.emoji}
            </div>
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2">
              <h1 className="text-sm font-bold text-white truncate">
                {agent ? `${agent.name} — ${agent.role}` : agentId}
              </h1>
            </div>
            <div className="flex items-center gap-3 mt-0.5">
              <ConnectionBadge status={connectionStatus} />
              {agent && (
                <span className="text-xs text-gray-600">
                  {agent.provider} · {agent.model?.split('-').slice(0, 2).join('-')}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.map(msg => (
            <MessageBubble key={msg.id} message={msg} agent={agent} />
          ))}

          {/* Typing indicator */}
          {isAgentTyping && (
            <MessageBubble
              message={{
                id: 'typing',
                type: 'typing',
                timestamp: Date.now() / 1000,
              }}
              agent={agent}
            />
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="flex-shrink-0 border-t border-gray-700/50 bg-gray-900/80 backdrop-blur-sm px-4 py-3">
          <div className="flex items-end gap-3">
            <button className="p-2 text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0">
              <Paperclip size={18} />
            </button>

            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                value={inputText}
                onChange={e => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Message ${agent?.name || 'agent'}... (Enter to send, Shift+Enter for newline)`}
                rows={1}
                className="w-full bg-gray-800/60 border border-gray-600/50 rounded-xl px-4 py-3 text-sm text-white
                  placeholder-gray-500 resize-none focus:outline-none focus:border-gray-500/70 focus:ring-1
                  focus:ring-gray-500/40 transition-all leading-relaxed"
                style={{ minHeight: '44px', maxHeight: '120px' }}
              />
            </div>

            <button
              onClick={handleSend}
              disabled={!inputText.trim() || connectionStatus !== 'connected'}
              className="p-2.5 rounded-xl transition-all flex-shrink-0 disabled:opacity-30 disabled:cursor-not-allowed"
              style={{
                backgroundColor: agent?.color || '#3B82F6',
                opacity: inputText.trim() && connectionStatus === 'connected' ? 1 : 0.3,
              }}
            >
              <Send size={16} className="text-white" />
            </button>
          </div>

          <div className="text-xs text-gray-700 mt-2 text-center">
            Press <kbd className="bg-gray-800 px-1 rounded text-gray-500">Enter</kbd> to send ·{' '}
            <kbd className="bg-gray-800 px-1 rounded text-gray-500">Shift+Enter</kbd> for newline
          </div>
        </div>
      </div>
    </div>
  );
}
