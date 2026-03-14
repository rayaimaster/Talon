import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { ChatMessage, Agent } from '../types';
import { ChevronDown, ChevronRight, Wrench, AlertCircle } from 'lucide-react';

interface MessageBubbleProps {
  message: ChatMessage;
  agent?: Agent;
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function ToolCallBubble({ message, agent }: { message: ChatMessage; agent?: Agent }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex items-start gap-3 animate-slide-in">
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center text-sm flex-shrink-0 mt-1"
        style={{ backgroundColor: (agent?.color || '#6B7280') + '33' }}
      >
        <Wrench size={14} style={{ color: agent?.color || '#9CA3AF' }} />
      </div>
      <div className="max-w-xl">
        <div className="bg-gray-700/50 rounded-2xl rounded-tl-sm border border-gray-600/50 overflow-hidden">
          {/* Tool call header */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-gray-700/50 transition-colors"
          >
            {expanded ? (
              <ChevronDown size={14} className="text-gray-400 flex-shrink-0" />
            ) : (
              <ChevronRight size={14} className="text-gray-400 flex-shrink-0" />
            )}
            <Wrench size={12} className="text-orange-400 flex-shrink-0" />
            <span className="text-sm font-mono text-orange-300 font-medium">
              {message.tool}
            </span>
            <span className="text-xs text-gray-500 ml-auto">
              {expanded ? 'Hide' : 'Show'} details
            </span>
          </button>

          {/* Expandable input */}
          {expanded && message.input && (
            <div className="px-4 pb-3 border-t border-gray-600/40">
              <div className="mt-2 text-xs text-gray-500 mb-1 font-medium uppercase tracking-wider">
                Input
              </div>
              <pre className="text-xs text-gray-300 font-mono bg-gray-800/60 rounded-lg p-3 overflow-auto max-h-32 whitespace-pre-wrap">
                {message.input}
              </pre>
            </div>
          )}
        </div>
        <div className="text-xs text-gray-600 mt-1 ml-1">{formatTime(message.timestamp)}</div>
      </div>
    </div>
  );
}

function ToolResultBubble({ message, agent }: { message: ChatMessage; agent?: Agent }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex items-start gap-3 animate-slide-in">
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center text-sm flex-shrink-0 mt-1"
        style={{ backgroundColor: (agent?.color || '#6B7280') + '33' }}
      >
        <span className="text-xs">✓</span>
      </div>
      <div className="max-w-xl">
        <div className="bg-gray-700/30 rounded-2xl rounded-tl-sm border border-gray-600/30 overflow-hidden">
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center gap-2 px-4 py-2 text-left hover:bg-gray-700/30 transition-colors"
          >
            {expanded ? (
              <ChevronDown size={14} className="text-gray-500 flex-shrink-0" />
            ) : (
              <ChevronRight size={14} className="text-gray-500 flex-shrink-0" />
            )}
            <span className="text-xs text-gray-400">
              <span className="font-mono text-green-400">{message.tool}</span> returned result
            </span>
          </button>

          {expanded && message.result && (
            <div className="px-4 pb-3 border-t border-gray-600/20">
              <pre className="mt-2 text-xs text-gray-400 font-mono bg-gray-800/40 rounded-lg p-3 overflow-auto max-h-40 whitespace-pre-wrap">
                {message.result}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TypingIndicator({ agent }: { agent?: Agent }) {
  return (
    <div className="flex items-end gap-3 animate-slide-in">
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center text-base flex-shrink-0"
        style={{ backgroundColor: (agent?.color || '#6B7280') + '22' }}
      >
        {agent?.emoji || '🤖'}
      </div>
      <div className="bg-gray-700/60 rounded-2xl rounded-bl-sm px-4 py-3">
        <div className="flex gap-1.5 items-center h-4">
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
}

export function MessageBubble({ message, agent }: MessageBubbleProps) {
  if (message.type === 'typing') {
    return <TypingIndicator agent={agent} />;
  }

  if (message.type === 'tool_call') {
    return <ToolCallBubble message={message} agent={agent} />;
  }

  if (message.type === 'tool_result') {
    return <ToolResultBubble message={message} agent={agent} />;
  }

  if (message.type === 'error') {
    return (
      <div className="flex justify-center animate-slide-in">
        <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-red-900/30 border border-red-500/30 text-red-400 text-sm max-w-lg">
          <AlertCircle size={14} className="flex-shrink-0" />
          {message.text}
        </div>
      </div>
    );
  }

  const isUser = message.role === 'user';

  return (
    <div
      className={`flex items-end gap-3 animate-slide-in ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar */}
      {!isUser && (
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-base flex-shrink-0"
          style={{ backgroundColor: (agent?.color || '#6B7280') + '22' }}
        >
          {agent?.emoji || '🤖'}
        </div>
      )}

      <div className={`flex flex-col max-w-xl ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Sender label */}
        {!isUser && (
          <div className="flex items-baseline gap-2 mb-1 ml-1">
            <span className="text-sm font-semibold" style={{ color: agent?.color || '#9CA3AF' }}>
              {message.agent || agent?.name || 'Agent'}
            </span>
            <span className="text-xs text-gray-600">{formatTime(message.timestamp)}</span>
          </div>
        )}

        {/* Message bubble */}
        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
            isUser
              ? 'bg-blue-600 text-white rounded-br-sm'
              : 'bg-gray-700/80 text-gray-100 rounded-bl-sm border border-gray-600/40'
          }`}
          style={
            !isUser && agent?.color
              ? { borderColor: agent.color + '22' }
              : undefined
          }
        >
          {isUser ? (
            <span className="whitespace-pre-wrap">{message.text}</span>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-pre:my-1 prose-ul:my-1 prose-ol:my-1">
            <ReactMarkdown
              components={{
                code({ node, className, children, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || '');
                  const isBlock = !props.inline && match;
                  return isBlock ? (
                    <SyntaxHighlighter
                      style={oneDark as any}
                      language={match![1]}
                      PreTag="div"
                      className="!my-2 !rounded-xl !text-xs"
                    >
                      {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                  ) : (
                    <code
                      className="bg-gray-800/80 text-orange-300 px-1.5 py-0.5 rounded text-xs font-mono"
                      {...props}
                    >
                      {children}
                    </code>
                  );
                },
              }}
            >
              {message.text || ''}
            </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Timestamp for user messages */}
        {isUser && (
          <span className="text-xs text-gray-600 mt-1 mr-1">{formatTime(message.timestamp)}</span>
        )}
      </div>
    </div>
  );
}
