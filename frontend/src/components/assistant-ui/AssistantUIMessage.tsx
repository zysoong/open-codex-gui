/**
 * AssistantUIMessage - Message component with proper tool streaming
 *
 * This component handles streaming and tool calls with proper chunk handling
 * for tool arguments and results.
 */

import React, { useMemo } from 'react';
import { Streamdown } from 'streamdown';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { DefaultToolFallback } from './DefaultToolFallback';

import type { ToolCallMessagePartProps, ToolCallMessagePartStatus } from '@assistant-ui/react';

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
      const toolCallsMap = new Map<string, ToolCallMessagePartProps>();

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
            };
            toolCallsMap.set(toolId, toolCall);
          }

          // Update partial args
          if (event.partial_args) {
            toolCall.args = event.partial_args;
            toolCall.argsText = JSON.stringify(event.partial_args, null, 2);
          } else if (event.content) {
            // Raw string content for args
            toolCall.argsText = event.content;
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
            };
            toolCallsMap.set(toolId, toolCall);
          } else {
            // Update with complete args
            toolCall.args = event.args || {};
            toolCall.argsText = JSON.stringify(event.args || {}, null, 2);
          }
        } else if (event.type === 'observation') {
          // Tool result - find the corresponding tool call
          const toolIds = Array.from(toolCallsMap.keys());
          const lastToolId = toolIds[toolIds.length - 1];

          if (lastToolId) {
            const toolCall = toolCallsMap.get(lastToolId);
            if (toolCall) {
              toolCall.result = event.content;
              toolCall.isError = !event.success;
              toolCall.status = { type: 'complete' };
            }
          }
        }
      });

      // Add accumulated text
      if (currentText) {
        parts.push({ type: 'text', content: currentText, isStreaming: true });
      }

      // Add tool calls
      toolCallsMap.forEach(toolCall => {
        parts.push({ type: 'tool-call', ...toolCall });
      });
    } else {
      // Non-streaming message
      if (message.content) {
        parts.push({ type: 'text', content: message.content, isStreaming: false });
      }

      console.log(message)

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
          <div key={index} style={{ position: 'relative' }}>
            <Streamdown>{part.content}</Streamdown>
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
      } else {
        return (
          <ReactMarkdown
            key={index}
            remarkPlugins={[remarkGfm]}
            components={{
              code({ inline, className, children, ...props }) {
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