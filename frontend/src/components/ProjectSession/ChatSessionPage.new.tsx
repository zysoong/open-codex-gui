import { useEffect, useRef, useMemo, useCallback, memo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tantml:invoke>
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { chatSessionsAPI, messagesAPI } from '@/services/api';
import { useStreamingManager } from './hooks/useStreamingManager';
import { MessageInput } from './components/MessageInput';
import './ChatSessionPage.css';

// ============================================================================
// HELPER COMPONENTS & FUNCTIONS (Keep existing ones)
// ============================================================================

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

const formatObservationContent = (content: string | any): string => {
  let dataToFormat = content;

  if (typeof content === 'object' && content !== null) {
    dataToFormat = content;
  } else if (typeof content === 'string') {
    try {
      dataToFormat = JSON.parse(content);
    } catch {
      return content.replace(/\\n/g, '\n');
    }
  }

  if (typeof dataToFormat === 'object' && dataToFormat !== null) {
    const resultValue = dataToFormat.result || dataToFormat.output || dataToFormat.data || dataToFormat;

    if (typeof resultValue === 'string') {
      return resultValue.replace(/\\n/g, '\n');
    }

    return JSON.stringify(resultValue, null, 2);
  }

  return String(dataToFormat);
};

const formatActionArgs = (args: string | any): string => {
  if (typeof args === 'object' && args !== null) {
    return JSON.stringify(args, null, 2);
  }

  if (typeof args === 'string') {
    try {
      const parsed = JSON.parse(args);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return args;
    }
  }

  return String(args);
};

const getFileExtension = (filePath: string): string => {
  const match = filePath.match(/\.([^.]+)$/);
  return match ? match[1].toLowerCase() : '';
};

const getLanguageFromExtension = (ext: string): string => {
  const langMap: { [key: string]: string } = {
    'js': 'javascript', 'jsx': 'javascript', 'ts': 'typescript', 'tsx': 'typescript',
    'py': 'python', 'rb': 'ruby', 'java': 'java', 'cpp': 'cpp', 'c': 'c',
    'cs': 'csharp', 'go': 'go', 'rs': 'rust', 'php': 'php', 'swift': 'swift',
    'kt': 'kotlin', 'scala': 'scala', 'sh': 'bash', 'bash': 'bash', 'zsh': 'bash',
    'yml': 'yaml', 'yaml': 'yaml', 'json': 'json', 'xml': 'xml', 'html': 'html',
    'css': 'css', 'scss': 'scss', 'sass': 'sass', 'sql': 'sql',
    'md': 'markdown', 'markdown': 'markdown',
  };
  return langMap[ext] || ext;
};

const FileWriteActionArgs = ({ args }: { args: any }) => {
  let parsedArgs = args;

  if (typeof args === 'string') {
    try {
      parsedArgs = JSON.parse(args);
    } catch {
      return <pre className="action-args">{args}</pre>;
    }
  }

  const filePath = parsedArgs.file_path || parsedArgs.path || parsedArgs.filename;
  const content = parsedArgs.content || parsedArgs.data;

  if (!filePath || !content) {
    return <pre className="action-args">{JSON.stringify(parsedArgs, null, 2)}</pre>;
  }

  const ext = getFileExtension(filePath);

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

// ============================================================================
// MESSAGE LIST COMPONENT (Optimized)
// ============================================================================

const MessagesList = memo(({
  visibleMessages,
  messages,
  visibleMessageCount,
  streamEvents,
  hasHiddenMessages,
  setVisibleMessageCount,
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

// ============================================================================
// MAIN CHAT SESSION PAGE (Redesigned)
// ============================================================================

export default function ChatSessionPage() {
  const { projectId, sessionId } = useParams<{ projectId: string; sessionId: string }>();
  const navigate = useNavigate();
  const [visibleMessageCount, setVisibleMessageCount] = useState(50);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Fetch session metadata
  const { data: session } = useQuery({
    queryKey: ['chatSession', sessionId],
    queryFn: () => chatSessionsAPI.get(sessionId!),
    enabled: !!sessionId,
  });

  // Fetch messages from API (optimized)
  const { data: messagesData } = useQuery({
    queryKey: ['messages', sessionId],
    queryFn: () => messagesAPI.list(sessionId!),
    enabled: !!sessionId,
    staleTime: 5 * 60 * 1000,        // 5 minutes
    cacheTime: 10 * 60 * 1000,       // 10 minutes
    refetchOnWindowFocus: false,     // Prevent black screen on tab switch
    refetchOnReconnect: false,
  });

  // Use streaming manager hook (encapsulates all WebSocket logic)
  const {
    messages,
    streamEvents,
    isStreaming,
    error,
    sendMessage,
    cancelStream,
    clearError,
  } = useStreamingManager({
    sessionId,
    initialMessages: messagesData?.messages || [],
  });

  // Handle pending message from sessionStorage (quick start feature)
  useEffect(() => {
    const pendingMessage = sessionStorage.getItem('pendingMessage');
    if (pendingMessage && sessionId) {
      sessionStorage.removeItem('pendingMessage');

      setTimeout(() => {
        sendMessage(pendingMessage);
      }, 500);
    }
  }, [sessionId, sendMessage]);

  // Compute visible messages
  const visibleMessages = useMemo(() => {
    if (!messages || messages.length === 0) return [];
    const startIndex = Math.max(0, messages.length - visibleMessageCount);
    return messages.slice(startIndex);
  }, [messages, visibleMessageCount]);

  const hasHiddenMessages = messages.length > visibleMessageCount;

  // Auto-scroll to bottom when message count changes
  useEffect(() => {
    if (isStreaming) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [messages.length, isStreaming]);

  // Memoized renderStreamEvent
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
  }, []);

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
              onClick={clearError}
              aria-label="Close error"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* Message Input (Isolated Component) */}
      <MessageInput
        onSend={sendMessage}
        onCancel={cancelStream}
        isStreaming={isStreaming}
      />
    </div>
  );
}
