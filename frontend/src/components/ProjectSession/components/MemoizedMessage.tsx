import { memo } from 'react';
import { Streamdown } from 'streamdown';
import { StreamEvent } from '../hooks/useOptimizedStreaming';
import {
  CodeBlock,
  FileWriteActionArgs,
  formatActionArgs,
  ObservationContent
} from './MessageHelpers';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  agent_actions?: any[];
}

interface MemoizedMessageProps {
  message: Message;
  isStreaming?: boolean;
  streamEvents?: StreamEvent[];
}

export const MemoizedMessage = memo(
  ({ message, isStreaming = false, streamEvents = [] }: MemoizedMessageProps) => {
    const hasPersistedActions = message.role === 'assistant' &&
                                message.agent_actions &&
                                Array.isArray(message.agent_actions) &&
                                message.agent_actions.length > 0;

    const renderStreamEvent = (event: StreamEvent, index: number) => {
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
              <ObservationContent content={event.content || ''} metadata={event.metadata} />
            </div>
          );

        default:
          return null;
      }
    };

    return (
      <div className={`message-wrapper ${message.role}`}>
        <div className="message-content">
          <div className="message-role">
            {message.role === 'user' ? (
              <div className="avatar user-avatar">You</div>
            ) : (
              <div className="avatar assistant-avatar">AI</div>
            )}
          </div>
          <div className="message-text">
            {/* Persisted Agent Actions */}
            {hasPersistedActions && (
              <div className="agent-actions-inline">
                {message.agent_actions!
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
                              <ObservationContent content={action.action_output} metadata={action.action_metadata} />
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
              </div>
            )}

            {/* Streaming Events (during active streaming) */}
            {message.role === 'assistant' && isStreaming && streamEvents.length > 0 && (
              <div className="message-body">
                {(() => {
                  const filteredEvents = streamEvents.filter((event: StreamEvent, idx: number, arr: StreamEvent[]) => {
                    if (event.type === 'action_streaming') {
                      return false;
                    }

                    if (event.type === 'action_args_chunk') {
                      const hasAction = arr.find(
                        (e: StreamEvent) => e.type === 'action' && e.tool === event.tool
                      );
                      if (hasAction) return false;

                      const laterChunk = arr.slice(idx + 1).find(
                        (e: StreamEvent) => e.type === 'action_args_chunk' && e.tool === event.tool
                      );
                      return !laterChunk;
                    }

                    return true;
                  });

                  const renderedElements: JSX.Element[] = [];
                  let accumulatedChunks = '';
                  let chunkStartIndex = 0;

                  filteredEvents.forEach((event: StreamEvent, idx: number) => {
                    if (event.type === 'chunk') {
                      if (accumulatedChunks === '') {
                        chunkStartIndex = idx;
                      }
                      accumulatedChunks += event.content || '';
                    } else {
                      if (accumulatedChunks) {
                        renderedElements.push(
                          <Streamdown key={`chunk-${chunkStartIndex}`}>
                            {accumulatedChunks}
                          </Streamdown>
                        );
                        accumulatedChunks = '';
                      }
                      const rendered = renderStreamEvent(event, idx);
                      if (rendered) {
                        renderedElements.push(rendered);
                      }
                    }
                  });

                  if (accumulatedChunks) {
                    renderedElements.push(
                      <Streamdown key={`chunk-${chunkStartIndex}`}>
                        {accumulatedChunks}
                      </Streamdown>
                    );
                  }

                  return renderedElements;
                })()}
                <span className="streaming-cursor">▋</span>
              </div>
            )}

            {/* Streaming message content (when streaming but no events) */}
            {message.role === 'assistant' && isStreaming && streamEvents.length === 0 && message.content && (
              <div className="message-body">
                <Streamdown>{message.content}</Streamdown>
                <span className="streaming-cursor">▋</span>
              </div>
            )}

            {/* Non-streaming assistant message */}
            {message.role === 'assistant' && !isStreaming && message.content && (
              <div className="message-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
                  {message.content}
                </ReactMarkdown>
              </div>
            )}

            {/* User message */}
            {message.role === 'user' && message.content && (
              <div className="message-body">
                <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{message.content}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  },
  (prevProps, nextProps) => {
    // Only re-render if content or streaming state actually changed
    return (
      prevProps.message.id === nextProps.message.id &&
      prevProps.message.content === nextProps.message.content &&
      prevProps.isStreaming === nextProps.isStreaming &&
      prevProps.streamEvents?.length === nextProps.streamEvents?.length
    );
  }
);

MemoizedMessage.displayName = 'MemoizedMessage';
