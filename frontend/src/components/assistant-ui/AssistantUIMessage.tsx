/**
 * AssistantUIMessage - Message component with proper tool streaming
 *
 * This component handles streaming and tool calls with proper chunk handling
 * for tool arguments and results.
 */

import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { DefaultToolFallback } from './DefaultToolFallback';
import { Message, StreamEvent } from '@/types';

import type { ToolCallMessagePartStatus } from '@assistant-ui/react';

// Simple streaming text component that doesn't use dynamic imports
const StreamingText: React.FC<{ content: string }> = ({ content }) => {
  // Simple markdown parsing without code highlighting during streaming
  const renderContent = () => {
    // Split by code blocks
    const parts = content.split(/(```[\s\S]*?```)/g);

    return parts.map((part, index) => {
      if (part.startsWith('```') && part.endsWith('```')) {
        // Extract code content
        const codeContent = part.slice(3, -3);
        const firstNewline = codeContent.indexOf('\n');
        const language = firstNewline > 0 ? codeContent.slice(0, firstNewline) : '';
        const code = firstNewline > 0 ? codeContent.slice(firstNewline + 1) : codeContent;

        return (
          <pre key={index} style={{
            backgroundColor: '#f6f8fa',
            padding: '12px',
            borderRadius: '6px',
            overflowX: 'auto',
            margin: '12px 0',
            fontSize: '13px',
            fontFamily: 'Monaco, Consolas, monospace'
          }}>
            <code>{code || language}</code>
          </pre>
        );
      } else {
        // Render regular text with basic markdown
        const formatted = part
          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
          .replace(/\*(.*?)\*/g, '<em>$1</em>')
          .replace(/`([^`]+)`/g, '<code style="background: #f6f8fa; padding: 2px 4px; border-radius: 3px;">$1</code>')
          .replace(/\n/g, '<br />');

        return (
          <span
            key={index}
            dangerouslySetInnerHTML={{ __html: formatted }}
          />
        );
      }
    });
  };

  return (
    <div style={{ position: 'relative' }}>
      {renderContent()}
      <span style={{
        display: 'inline-block',
        width: '8px',
        height: '20px',
        backgroundColor: '#111827',
        marginLeft: '2px',
        animation: 'blink 1s infinite',
      }} />
    </div>
  );
};

interface AssistantUIMessageProps {
  message: Message;
  isStreaming?: boolean;
  streamEvents?: StreamEvent[];
}

export const AssistantUIMessage: React.FC<AssistantUIMessageProps> = ({
  message,
  isStreaming = false,
  streamEvents = [],
}) => {
  // Process message parts with proper streaming support
  const messageParts = useMemo(() => {
    const parts: any[] = [];
    let currentText = '';

    // Handle streaming events with proper chunking
    if (isStreaming && streamEvents.length > 0) {
      // Use an array to maintain order instead of Map
      const toolCalls: Array<any> = [];
      const toolCallsMap = new Map<string, any>();
      let toolCallOrder = 0;

      streamEvents.forEach((event: StreamEvent) => {
        if (event.type === 'chunk') {
          // Accumulate text chunks
          currentText += event.content || '';
        } else if (event.type === 'action_args_chunk') {
          // Streaming tool arguments
          const toolId = `${event.tool}-stream`;
          let toolCall = toolCallsMap.get(toolId);

          if (!toolCall) {
            toolCall = {
              toolCallId: toolId,
              toolName: event.tool || 'unknown',
              args: {},
              argsText: '',
              status: { type: 'running' } as ToolCallMessagePartStatus,
              addResult: () => {},
              resume: () => {},
              order: toolCallOrder++,
            };
            toolCallsMap.set(toolId, toolCall);
            toolCalls.push(toolCall);
          } else {
            // Update partial args - create new object
            const updatedToolCall = {
              ...toolCall,
              args: event.partial_args || toolCall.args,
              argsText: event.partial_args ? JSON.stringify(event.partial_args, null, 2) :
                       event.content || toolCall.argsText,
            };
            toolCallsMap.set(toolId, updatedToolCall);
            const index = toolCalls.findIndex(tc => tc.toolCallId === toolId);
            if (index !== -1) {
              toolCalls[index] = updatedToolCall;
            }
          }
        } else if (event.type === 'action') {
          // Complete tool call with full arguments
          const toolId = `${event.tool}-stream`;
          let toolCall = toolCallsMap.get(toolId);

          if (!toolCall) {
            toolCall = {
              toolCallId: toolId,
              toolName: event.tool || 'unknown',
              args: event.args || {},
              argsText: JSON.stringify(event.args || {}, null, 2),
              status: { type: 'running' } as ToolCallMessagePartStatus,
              addResult: () => {},
              resume: () => {},
              order: toolCallOrder++,
            };
            toolCallsMap.set(toolId, toolCall);
            toolCalls.push(toolCall);
          } else {
            // Update with complete args - create new object
            const updatedToolCall = {
              ...toolCall,
              args: event.args || {},
              argsText: JSON.stringify(event.args || {}, null, 2),
            };
            toolCallsMap.set(toolId, updatedToolCall);
            const index = toolCalls.findIndex(tc => tc.toolCallId === toolId);
            if (index !== -1) {
              toolCalls[index] = updatedToolCall;
            }
          }
        } else if (event.type === 'observation') {
          // Tool result - find the corresponding tool call
          const toolIds = Array.from(toolCallsMap.keys());
          const lastToolId = toolIds[toolIds.length - 1];

          if (lastToolId) {
            const toolCall = toolCallsMap.get(lastToolId);
            if (toolCall) {
              // Update with result - create new object
              const updatedToolCall = {
                ...toolCall,
                result: event.content,
                isError: !event.success,
                status: { type: 'complete' },
              };
              toolCallsMap.set(lastToolId, updatedToolCall);
              const index = toolCalls.findIndex(tc => tc.toolCallId === lastToolId);
              if (index !== -1) {
                toolCalls[index] = updatedToolCall;
              }
            }
          }
        }
      });

      // Add accumulated text
      if (currentText) {
        parts.push({ type: 'text', content: currentText, isStreaming: true });
      }

      // Add tool calls sorted by their order of appearance
      toolCalls
        .sort((a, b) => a.order - b.order)
        .forEach(toolCall => {
          const { order, ...rest } = toolCall;
          parts.push({ type: 'tool-call', ...rest });
        });
    } else {
      // Non-streaming message
      if (message.content) {
        parts.push({ type: 'text', content: message.content, isStreaming: false });
      }

      // Add persisted agent actions as tool calls
      if (message.agent_actions && Array.isArray(message.agent_actions)) {
        message.agent_actions
          .slice()
          .sort((a: any, b: any) => {
            const timeA = new Date(a.created_at).getTime();
            const timeB = new Date(b.created_at).getTime();
            return timeA - timeB;
          })
          .forEach((action: any) => {
            parts.push({
              type: 'tool-call',
              toolCallId: action.id || `action-${Date.now()}-${Math.random()}`,
              toolName: action.action_type || 'unknown',
              args: action.action_input || {},
              argsText: JSON.stringify(action.action_input || {}, null, 2),
              result: action.action_metadata.is_binary ? action.action_metadata : action.action_output,
              isError: action.status !== 'success',
              status: { type: 'complete' } as ToolCallMessagePartStatus,
              addResult: () => {},
              resume: () => {},
            });
          });
      }
    }

    return parts;
  }, [message, isStreaming, streamEvents]);

  const renderPart = (part: any, index: number) => {
    if (part.type === 'text') {
      if (part.isStreaming) {
        return (
          <StreamingText key={index} content={part.content} />
        );
      } else {
        return (
          <ReactMarkdown
            key={index}
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children, ...props }: any) {
                const match = /language-(\w+)/.exec(className || '');
                const language = match ? match[1] : '';
                const isInline = !props.node || props.node.position?.start.line === props.node.position?.end.line;

                return !isInline && language ? (
                  <SyntaxHighlighter
                    style={oneLight as any}
                    language={language}
                    PreTag="div"
                    customStyle={{
                      margin: '12px 0',
                      borderRadius: '6px',
                      border: '1px solid #e5e7eb',
                      fontSize: '13px',
                    }}
                  >
                    {String(children).replace(/\n$/, '')}
                  </SyntaxHighlighter>
                ) : (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              }
            }}
          >
            {part.content}
          </ReactMarkdown>
        );
      }
    } else if (part.type === 'tool-call') {
      // Use DefaultToolFallback for all tool calls
      return <DefaultToolFallback key={index} {...part} />;
    }
    return null;
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
          <div className="message-body">
            {messageParts.map((part, index) => renderPart(part, index))}
          </div>
        </div>
      </div>
    </div>
  );
};