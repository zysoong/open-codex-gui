import { useEffect, useRef, useState, useCallback, memo, useMemo, Profiler } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { chatSessionsAPI, messagesAPI } from '@/services/api';
import { useChatStore } from '@/stores/chatStore';
import './ChatSessionPage.css';

// Custom code component with syntax highlighting
const CodeBlock = ({ inline, className, children, ...props }: any) => {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';

  return !inline && language ? (
    <SyntaxHighlighter
      style={oneLight}
      language={language}
      PreTag="div"
      customStyle={{
        margin: '12px 0',
        borderRadius: '6px',
        border: '1px solid #e5e7eb',
        fontSize: '13px',
      }}
      {...props}
    >
      {String(children).replace(/\n$/, '')}
    </SyntaxHighlighter>
  ) : (
    <code className={className} {...props}>
      {children}
    </code>
  );
};

// Helper function to format observation content
const formatObservationContent = (content: string | any): string => {
  let dataToFormat = content;

  // If content is already an object, use it directly
  if (typeof content === 'object' && content !== null) {
    dataToFormat = content;
  } else if (typeof content === 'string') {
    // Try to parse as JSON
    try {
      dataToFormat = JSON.parse(content);
    } catch {
      // If not JSON, just use the string as-is
      // Replace escaped newlines with actual newlines
      return content.replace(/\\n/g, '\n');
    }
  }

  // If we have a parsed object, extract the result/output field
  if (typeof dataToFormat === 'object' && dataToFormat !== null) {
    // Try common result field names
    const resultValue = dataToFormat.result || dataToFormat.output || dataToFormat.data || dataToFormat;

    // If the result is a string, format it
    if (typeof resultValue === 'string') {
      return resultValue.replace(/\\n/g, '\n');
    }

    // If it's still an object, stringify it nicely
    return JSON.stringify(resultValue, null, 2);
  }

  return String(dataToFormat);
};

// Helper function to pretty print action arguments
const formatActionArgs = (args: string | any): string => {
  // If args is already an object, stringify it
  if (typeof args === 'object' && args !== null) {
    return JSON.stringify(args, null, 2);
  }

  // If args is a string, try to parse and re-stringify
  if (typeof args === 'string') {
    try {
      const parsed = JSON.parse(args);
      return JSON.stringify(parsed, null, 2);
    } catch {
      // If not valid JSON, return as-is
      return args;
    }
  }

  return String(args);
};

// Helper to get file extension from path
const getFileExtension = (filePath: string): string => {
  const match = filePath.match(/\.([^.]+)$/);
  return match ? match[1].toLowerCase() : '';
};

// Helper to get language from file extension for syntax highlighting
const getLanguageFromExtension = (ext: string): string => {
  const langMap: { [key: string]: string } = {
    'js': 'javascript',
    'jsx': 'javascript',
    'ts': 'typescript',
    'tsx': 'typescript',
    'py': 'python',
    'rb': 'ruby',
    'java': 'java',
    'cpp': 'cpp',
    'c': 'c',
    'cs': 'csharp',
    'go': 'go',
    'rs': 'rust',
    'php': 'php',
    'swift': 'swift',
    'kt': 'kotlin',
    'scala': 'scala',
    'sh': 'bash',
    'bash': 'bash',
    'zsh': 'bash',
    'yml': 'yaml',
    'yaml': 'yaml',
    'json': 'json',
    'xml': 'xml',
    'html': 'html',
    'css': 'css',
    'scss': 'scss',
    'sass': 'sass',
    'sql': 'sql',
    'md': 'markdown',
    'markdown': 'markdown',
  };
  return langMap[ext] || ext;
};

// Component to render file write action arguments
const FileWriteActionArgs = ({ args }: { args: any }) => {
  let parsedArgs = args;

  // Parse if string
  if (typeof args === 'string') {
    try {
      parsedArgs = JSON.parse(args);
    } catch {
      return <pre className="action-args">{args}</pre>;
    }
  }

  // Extract file_path and content
  const filePath = parsedArgs.file_path || parsedArgs.path || parsedArgs.filename;
  const content = parsedArgs.content || parsedArgs.data;

  if (!filePath || !content) {
    return <pre className="action-args">{JSON.stringify(parsedArgs, null, 2)}</pre>;
  }

  const ext = getFileExtension(filePath);

  // Check if it's an image
  if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp'].includes(ext)) {
    return (
      <div className="action-args">
        <div style={{ marginBottom: '8px', fontWeight: 600 }}>
          Writing image: {filePath}
        </div>
        <div style={{ color: '#6b7280', fontSize: '12px' }}>
          (Image preview not available for base64 content)
        </div>
      </div>
    );
  }

  // Check if it's markdown
  if (['md', 'markdown'].includes(ext)) {
    return (
      <div className="action-args">
        <div style={{ marginBottom: '8px', fontWeight: 600 }}>
          Writing markdown: {filePath}
        </div>
        <div style={{
          background: '#f9fafb',
          border: '1px solid #e5e7eb',
          borderRadius: '6px',
          padding: '12px',
          marginTop: '8px'
        }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
            {content}
          </ReactMarkdown>
        </div>
      </div>
    );
  }

  // For code files, show with syntax highlighting
  const language = getLanguageFromExtension(ext);

  return (
    <div className="action-args">
      <div style={{ marginBottom: '8px', fontWeight: 600 }}>
        Writing file: {filePath}
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneLight}
        customStyle={{
          margin: '8px 0 0 0',
          borderRadius: '6px',
          border: '1px solid #e5e7eb',
          fontSize: '13px',
        }}
      >
        {content}
      </SyntaxHighlighter>
    </div>
  );
};

// Memoized message list to prevent re-renders when input changes
const MessagesList = memo(({
  visibleMessages,
  messages,
  visibleMessageCount,
  streamEvents,
  hasHiddenMessages,
  setVisibleMessageCount,
  formatActionArgs,
  formatObservationContent,
  renderStreamEvent
}: any) => {
  return (
    <>
      {hasHiddenMessages && (
        <div style={{ textAlign: 'center', padding: '12px' }}>
          <button
            onClick={() => setVisibleMessageCount((prev: number) => prev + 50)}
            style={{
              padding: '8px 16px',
              background: '#4a90e2',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '14px'
            }}
          >
            Load {Math.min(50, messages.length - visibleMessageCount)} older messages
          </button>
        </div>
      )}
      {visibleMessages.map((message: any, visibleIndex: number) => {
        // Calculate actual index in full messages array
        const startIndex = Math.max(0, messages.length - visibleMessageCount);
        const actualIndex = startIndex + visibleIndex;
        const isLastMessage = actualIndex === messages.length - 1;

        return (
          <div key={message.id || visibleIndex} className={`message-wrapper ${message.role}`}>
            <div className="message-content">
              <div className="message-role">
                {message.role === 'user' ? (
                  <div className="avatar user-avatar">You</div>
                ) : (
                  <div className="avatar assistant-avatar">AI</div>
                )}
              </div>
              <div className="message-text">
                {(() => {
                  const hasPersistedActions = message.role === 'assistant' &&
                                              message.agent_actions &&
                                              Array.isArray(message.agent_actions) &&
                                              message.agent_actions.length > 0;

                  return hasPersistedActions ? (
                    <div className="agent-actions-inline">
                      {message.agent_actions
                        .slice()
                        .sort((a: any, b: any) => {
                          const timeA = new Date(a.created_at).getTime();
                          const timeB = new Date(b.created_at).getTime();
                          return timeA - timeB;
                        })
                        .map((action: any, idx: number) => {
                        const isFileWrite = action.action_type && (
                          action.action_type.toLowerCase().includes('file_write') ||
                          action.action_type.toLowerCase().includes('write_file') ||
                          action.action_type.toLowerCase().includes('writefile')
                        );

                        return (
                          <div key={idx} className="action-block action-action">
                            <div className="action-usage">
                              <div className="action-header">
                                <span className="action-icon">🔧</span>
                                <strong>Used {action.action_type}</strong>
                              </div>
                              {action.action_input && (
                                isFileWrite ? (
                                  <FileWriteActionArgs args={action.action_input} />
                                ) : (
                                  <pre className="action-args">{formatActionArgs(action.action_input)}</pre>
                                )
                              )}
                              {action.action_output && (
                                <div className={`observation ${action.status === 'success' ? 'success' : 'error'}`}>
                                  <div className="observation-header">
                                    <span className="observation-icon">
                                      {action.status === 'success' ? '✅' : '❌'}
                                    </span>
                                    <strong>Result</strong>
                                  </div>
                                  <pre className="observation-content">{formatObservationContent(action.action_output)}</pre>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : null;
                })()}

                {message.role === 'assistant' && isLastMessage && streamEvents && streamEvents.length > 0 && (
                  <div className="message-body">
                    {(() => {
                      const filteredEvents = streamEvents.filter((event: any, idx: number, arr: any[]) => {
                        if (event.type === 'action_streaming') {
                          return false;
                        }

                        if (event.type === 'action_args_chunk') {
                          const hasAction = arr.find(
                            (e: any) => e.type === 'action' && e.tool === event.tool
                          );
                          if (hasAction) return false;

                          const laterChunk = arr.slice(idx + 1).find(
                            (e: any) => e.type === 'action_args_chunk' && e.tool === event.tool
                          );
                          return !laterChunk;
                        }

                        return true;
                      });

                      const renderedElements: JSX.Element[] = [];
                      let accumulatedChunks = '';
                      let chunkStartIndex = 0;

                      filteredEvents.forEach((event: any, idx: number) => {
                        if (event.type === 'chunk') {
                          if (accumulatedChunks === '') {
                            chunkStartIndex = idx;
                          }
                          accumulatedChunks += event.content;
                        } else {
                          if (accumulatedChunks) {
                            renderedElements.push(
                              <ReactMarkdown
                                key={`chunk-${chunkStartIndex}`}
                                remarkPlugins={[remarkGfm]}
                                components={{ code: CodeBlock }}
                              >
                                {accumulatedChunks}
                              </ReactMarkdown>
                            );
                            accumulatedChunks = '';
                          }
                          renderedElements.push(renderStreamEvent(event, idx));
                        }
                      });

                      if (accumulatedChunks) {
                        renderedElements.push(
                          <ReactMarkdown
                            key={`chunk-${chunkStartIndex}`}
                            remarkPlugins={[remarkGfm]}
                            components={{ code: CodeBlock }}
                          >
                            {accumulatedChunks}
                          </ReactMarkdown>
                        );
                      }

                      return renderedElements;
                    })()}
                    <span className="streaming-cursor">▋</span>
                  </div>
                )}

                {message.role === 'assistant' && isLastMessage && (!streamEvents || streamEvents.length === 0) && message.content && (
                  <div className="message-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
                      {message.content}
                    </ReactMarkdown>
                    <span className="streaming-cursor">▋</span>
                  </div>
                )}

                {message.role === 'assistant' && !isLastMessage && message.content && (
                  <div className="message-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
                      {message.content}
                    </ReactMarkdown>
                  </div>
                )}

                {message.role === 'user' && message.content && (
                  <div className="message-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
                      {message.content}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
});

MessagesList.displayName = 'MessagesList';

export default function ChatSessionPage() {
  const { projectId, sessionId } = useParams<{ projectId: string; sessionId: string }>();
  const navigate = useNavigate();
  const {
    agentActions,
    addAgentAction,
    clearAgentActions,
    streamEvents,
    addStreamEvent,
    clearStreamEvents
  } = useChatStore();
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [visibleMessageCount, setVisibleMessageCount] = useState(50); // Show last 50 messages
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();

  // Fetch session
  const { data: session } = useQuery({
    queryKey: ['chatSession', sessionId],
    queryFn: () => chatSessionsAPI.get(sessionId!),
    enabled: !!sessionId,
  });

  // Fetch messages
  const { data: messagesData, refetch: refetchMessages } = useQuery({
    queryKey: ['messages', sessionId],
    queryFn: () => messagesAPI.list(sessionId!),
    enabled: !!sessionId,
    staleTime: 0, // Always refetch on mount
    cacheTime: 0, // Don't cache
  });

  // Load messages from API
  useEffect(() => {
    if (messagesData?.messages) {
      setMessages(messagesData.messages);
    }
  }, [messagesData]);

  // Check for pending message from quick start
  useEffect(() => {
    const pendingMessage = sessionStorage.getItem('pendingMessage');
    if (pendingMessage && sessionId && wsRef.current) {
      sessionStorage.removeItem('pendingMessage');
      // Send it automatically after WebSocket is ready
      setTimeout(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          setIsSending(true);

          const userMsg = {
            id: 'temp-user-' + Date.now(),
            role: 'user' as const,
            content: pendingMessage,
            created_at: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, userMsg]);

          wsRef.current.send(
            JSON.stringify({
              type: 'message',
              content: pendingMessage,
            })
          );
        }
      }, 500);
    }
  }, [sessionId, wsRef.current]);

  // Compute visible messages (only render last N messages for performance)
  const visibleMessages = useMemo(() => {
    if (!messages || messages.length === 0) return [];
    const startIndex = Math.max(0, messages.length - visibleMessageCount);
    return messages.slice(startIndex);
  }, [messages, visibleMessageCount]);

  const hasHiddenMessages = messages.length > visibleMessageCount;

  // Auto-scroll to bottom only when sending (not on every stream event)
  useEffect(() => {
    if (isSending) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [messages.length]); // Only when message count changes

  // Memoized renderStreamEvent to prevent re-renders
  const renderStreamEvent = useCallback((event: any, index: number) => {
    switch (event.type) {
      case 'chunk':
        return <span key={index}>{event.content}</span>;

      case 'thought':
        return (
          <details key={index} className="thought-details" open>
            <summary>💭 Thinking... (Step {event.step})</summary>
            <div className="thought-content">{event.content}</div>
          </details>
        );

      case 'action_args_chunk':
        return (
          <div key={index} className="action-usage args-streaming">
            <div className="action-header">
              <span className="action-icon">📝</span>
              <strong>{event.tool}</strong>
            </div>
            <pre className="action-args partial">{formatActionArgs(event.partial_args || event.content)}</pre>
          </div>
        );

      case 'action':
        // Check if this is a file write action
        const isFileWrite = event.tool && (
          event.tool.toLowerCase().includes('file_write') ||
          event.tool.toLowerCase().includes('write_file') ||
          event.tool.toLowerCase().includes('writefile')
        );

        return (
          <div key={index} className="action-usage">
            <div className="action-header">
              <span className="action-icon">🔧</span>
              <strong>Using {event.tool}</strong>
            </div>
            {event.args && (
              isFileWrite ? (
                <FileWriteActionArgs args={event.args} />
              ) : (
                <pre className="action-args">{formatActionArgs(event.args)}</pre>
              )
            )}
          </div>
        );

      case 'observation':
        return (
          <div key={index} className={`observation ${event.success ? 'success' : 'error'}`}>
            <div className="observation-header">
              <span className="observation-icon">
                {event.success ? '✅' : '❌'}
              </span>
              <strong>Result</strong>
            </div>
            <pre className="observation-content">{formatObservationContent(event.content)}</pre>
          </div>
        );

      default:
        return null;
    }
  }, []); // No dependencies since formatActionArgs and formatObservationContent are stable

  // WebSocket connection
  useEffect(() => {
    if (!sessionId) return;

    const ws = new WebSocket(`ws://127.0.0.1:8000/api/v1/chats/${sessionId}/stream`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'start') {
        setIsSending(true); // Enable stop button
        clearAgentActions();
        clearStreamEvents(); // Clear unified stream
        setMessages((prev) => [
          ...prev,
          {
            id: 'temp-' + Date.now(),
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
          },
        ]);
      } else if (data.type === 'cancelled') {
        setIsSending(false);
      } else if (data.type === 'thought') {
        const thought = {
          type: 'thought' as const,
          content: data.content,
          step: data.step,
        };
        addAgentAction(thought);
        addStreamEvent(thought);
      } else if (data.type === 'action_streaming') {
        const streamingAction = {
          type: 'action_streaming' as const,
          content: `Preparing ${data.tool}...`,
          tool: data.tool,
          status: data.status,
          step: data.step,
        };
        addAgentAction(streamingAction);
        addStreamEvent(streamingAction);
      } else if (data.type === 'action_args_chunk') {
        const argsChunk = {
          type: 'action_args_chunk' as const,
          content: data.partial_args || '',
          tool: data.tool,
          partial_args: data.partial_args,
          step: data.step,
        };
        addAgentAction(argsChunk);
        addStreamEvent(argsChunk);
      } else if (data.type === 'action') {
        const action = {
          type: 'action' as const,
          content: `Using tool: ${data.tool}`,
          tool: data.tool,
          args: data.args,
          step: data.step,
        };
        addAgentAction(action);
        addStreamEvent(action);
      } else if (data.type === 'observation') {
        const observation = {
          type: 'observation' as const,
          content: data.content,
          success: data.success,
          step: data.step,
        };
        addAgentAction(observation);
        addStreamEvent(observation);
      } else if (data.type === 'chunk') {
        // Add chunk to unified stream
        addStreamEvent({
          type: 'chunk',
          content: data.content,
        });
        // Update the last message with new content
        setMessages((prev) => {
          const newMessages = [...prev];
          const lastMsg = newMessages[newMessages.length - 1];
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.content += data.content;
          }
          return newMessages;
        });
      } else if (data.type === 'end') {
        setIsSending(false);
        // Clear stream events
        clearStreamEvents();
        // Invalidate and refetch messages immediately
        queryClient.invalidateQueries({ queryKey: ['messages', sessionId] });
      } else if (data.type === 'error') {
        console.error('WebSocket error:', data.content);
        setError(data.content || 'An error occurred');
        setIsSending(false);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsSending(false);
    };

    ws.onclose = () => {
      console.log('WebSocket closed');
      setIsSending(false);
    };

    return () => {
      console.log('[ChatSessionPage] Cleaning up WebSocket');
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]); // Only sessionId - store functions are stable

  const handleSend = async (messageText?: string) => {
    const textToSend = messageText || input;
    if (!textToSend.trim() || isSending || !wsRef.current) return;

    setError(null); // Clear any previous errors
    setInput('');

    // Add user message to UI
    const userMsg = {
      id: 'temp-user-' + Date.now(),
      role: 'user' as const,
      content: textToSend,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // Send via WebSocket (isSending will be set to true when 'start' event is received)
    wsRef.current.send(
      JSON.stringify({
        type: 'message',
        content: textToSend,
      })
    );
  };

  const handleCancel = () => {
    console.log('[ChatSessionPage] Cancel button clicked');
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'cancel' }));
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-session-page">
      {/* Header */}
      <div className="chat-header">
        <button className="back-btn" onClick={() => navigate(`/projects/${projectId}`)}>
          ← Back to Project
        </button>
        <h2 className="session-title">
          {session?.name || 'Chat Session'}
          {session?.environment_type && (
            <span className="environment-badge" title="Sandbox environment">
              {session.environment_type}
            </span>
          )}
        </h2>
        <div className="header-spacer"></div>
      </div>

      {/* Messages */}
      <div className="chat-messages-container">
        <div className="chat-messages">
          {!messages || messages.length === 0 ? (
            <div className="empty-chat">
              <h3>Start a conversation</h3>
              <p>Ask me anything, and I'll help you with code, data analysis, and more.</p>
            </div>
          ) : (
            <MessagesList
              visibleMessages={visibleMessages}
              messages={messages}
              visibleMessageCount={visibleMessageCount}
              streamEvents={streamEvents}
              hasHiddenMessages={hasHiddenMessages}
              setVisibleMessageCount={setVisibleMessageCount}
              formatActionArgs={formatActionArgs}
              formatObservationContent={formatObservationContent}
              renderStreamEvent={renderStreamEvent}
            />
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="chat-error-banner">
          <div className="error-content">
            <span className="error-icon">⚠️</span>
            <div className="error-message">{error}</div>
            <button
              className="error-close-btn"
              onClick={() => setError(null)}
              aria-label="Close error"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="chat-input-container">
        <div className="chat-input-wrapper">
          <textarea
            className="chat-input"
            placeholder="Type your message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            rows={1}
            disabled={isSending}
          />
          <button
            className={`send-btn ${isSending ? 'stop-btn' : ''}`}
            onClick={isSending ? handleCancel : () => handleSend()}
            disabled={isSending ? false : !input.trim()}
            title={isSending ? 'Stop generating' : 'Send message'}
          >
            {isSending ? (
              'Stop'
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path
                  d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
