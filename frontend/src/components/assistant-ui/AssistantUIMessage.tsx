/**
 * AssistantUIMessage - Message component with ContentBlock support
 *
 * This component renders ContentBlocks with proper streaming and tool call handling.
 * It receives a main block (user_text or assistant_text) and optional tool blocks
 * (tool_call and tool_result) that are associated with this message.
 */

import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { DefaultToolFallback } from './DefaultToolFallback';
import { ContentBlock, StreamEvent } from '@/types';

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
  block: ContentBlock;
  toolBlocks?: ContentBlock[];
  isStreaming?: boolean;
  streamEvents?: StreamEvent[];
}

export const AssistantUIMessage: React.FC<AssistantUIMessageProps> = ({
  block,
  toolBlocks = [],
  isStreaming = false,
  streamEvents = [],
}) => {
  // Determine role from block type
  const role = block.block_type === 'user_text' ? 'user' : 'assistant';
  const textContent = block.content?.text || '';

  // Process message parts with proper streaming support
  const messageParts = useMemo(() => {
    const parts: any[] = [];

    // Handle streaming events with proper chunking
    if (isStreaming && streamEvents.length > 0) {
      // Accumulate text from streaming events
      let streamingText = '';
      const toolCalls: Array<any> = [];
      const toolCallsMap = new Map<string, any>();
      let toolCallOrder = 0;

      streamEvents.forEach((event: StreamEvent) => {
        if (event.type === 'chunk') {
          streamingText += event.content || '';
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
        } else if (event.type === 'tool_call_block' && event.block) {
          // Handle tool_call_block event
          const blockContent = event.block.content as any;
          const toolId = event.block.id;
          const toolCall = {
            toolCallId: toolId,
            toolName: blockContent.tool_name || 'unknown',
            args: blockContent.arguments || {},
            argsText: JSON.stringify(blockContent.arguments || {}, null, 2),
            status: { type: blockContent.status === 'complete' ? 'complete' : 'running' } as ToolCallMessagePartStatus,
            addResult: () => {},
            resume: () => {},
            order: toolCallOrder++,
          };
          toolCallsMap.set(toolId, toolCall);
          toolCalls.push(toolCall);
        } else if (event.type === 'tool_result_block' && event.block) {
          // Handle tool_result_block event
          const blockContent = event.block.content as any;
          const parentId = event.block.parent_block_id;

          if (parentId && toolCallsMap.has(parentId)) {
            const toolCall = toolCallsMap.get(parentId);
            const updatedToolCall = {
              ...toolCall,
              result: blockContent.result,
              isError: !blockContent.success,
              status: { type: 'complete' },
            };
            toolCallsMap.set(parentId, updatedToolCall);
            const index = toolCalls.findIndex(tc => tc.toolCallId === parentId);
            if (index !== -1) {
              toolCalls[index] = updatedToolCall;
            }
          }
        }
      });

      // Add streaming text (combine with base text content)
      const combinedText = textContent + streamingText;
      if (combinedText) {
        parts.push({ type: 'text', content: combinedText, isStreaming: true });
      }

      // Add tool calls sorted by order
      toolCalls
        .sort((a, b) => a.order - b.order)
        .forEach(toolCall => {
          const { order, ...rest } = toolCall;
          parts.push({ type: 'tool-call', ...rest });
        });
    } else {
      // Non-streaming message
      if (textContent) {
        parts.push({ type: 'text', content: textContent, isStreaming: false });
      }

      // Add persisted tool blocks
      if (toolBlocks && Array.isArray(toolBlocks) && toolBlocks.length > 0) {
        // Sort by sequence_number
        const sortedBlocks = [...toolBlocks].sort((a, b) => a.sequence_number - b.sequence_number);

        // Group tool_call with their tool_result
        const toolCallMap = new Map<string, { call: ContentBlock; result?: ContentBlock }>();

        for (const toolBlock of sortedBlocks) {
          if (toolBlock.block_type === 'tool_call') {
            toolCallMap.set(toolBlock.id, { call: toolBlock });
          } else if (toolBlock.block_type === 'tool_result') {
            const parentId = toolBlock.parent_block_id;
            if (parentId && toolCallMap.has(parentId)) {
              const entry = toolCallMap.get(parentId)!;
              entry.result = toolBlock;
            } else {
              // Orphan result - show anyway
              const callContent = toolBlock.content as any;
              parts.push({
                type: 'tool-call',
                toolCallId: toolBlock.id,
                toolName: callContent.tool_name || 'unknown',
                args: {},
                argsText: '{}',
                result: callContent.result,
                isError: !callContent.success,
                status: { type: 'complete' } as ToolCallMessagePartStatus,
                addResult: () => {},
                resume: () => {},
              });
            }
          }
        }

        // Convert to parts
        toolCallMap.forEach(({ call, result }) => {
          const callContent = call.content as any;
          const resultContent = result?.content as any;

          parts.push({
            type: 'tool-call',
            toolCallId: call.id,
            toolName: callContent.tool_name || 'unknown',
            args: callContent.arguments || {},
            argsText: JSON.stringify(callContent.arguments || {}, null, 2),
            result: resultContent?.result || resultContent?.error,
            isError: resultContent ? !resultContent.success : false,
            status: { type: result ? 'complete' : (callContent.status === 'running' ? 'running' : 'complete') } as ToolCallMessagePartStatus,
            addResult: () => {},
            resume: () => {},
            // Include binary data if present
            ...(result?.block_metadata?.type === 'image' ? {
              result: result.block_metadata,
            } : {}),
          });
        });
      }
    }

    return parts;
  }, [block, toolBlocks, isStreaming, streamEvents, textContent]);

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
    <div className={`message-wrapper ${role}`}>
      <div className="message-content">
        <div className="message-role">
          {role === 'user' ? (
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
