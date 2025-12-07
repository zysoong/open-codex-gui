/**
 * AssistantUIMessage - Message component with ContentBlock support
 *
 * This component renders ContentBlocks with proper streaming and tool call handling.
 * Uses sequence_number from blocks for ordering, overlays streaming state on top.
 */

import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { DefaultToolFallback } from './DefaultToolFallback';
import { ContentBlock, StreamEvent } from '@/types';

import type { ToolCallMessagePartStatus } from '@assistant-ui/react';

// Simple streaming text component
const StreamingText: React.FC<{ content: string }> = ({ content }) => {
  const renderContent = () => {
    const parts = content.split(/(```[\s\S]*?```)/g);

    return parts.map((part, index) => {
      if (part.startsWith('```') && part.endsWith('```')) {
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
  const role = block.block_type === 'user_text' ? 'user' : 'assistant';
  const textContent = block.content?.text || '';

  // Build message parts
  const messageParts = useMemo(() => {
    const parts: any[] = [];

    // Step 1: Build streaming tool state from events (latest state for each tool)
    const streamingState = new Map<string, {
      toolName: string;
      argsText: string;
      args: any;
      status: string;
      result?: any;
      isError?: boolean;
      step: number;
    }>();

    let streamingText = '';

    if (streamEvents.length > 0) {
      // Process ALL events to get final state for each streaming tool
      for (const event of streamEvents) {
        if (event.type === 'chunk') {
          streamingText += event.content || '';
        } else if (event.type === 'action_args_chunk') {
          const key = `${event.tool}-${event.step || 0}`;
          const argsString = event.partial_args || event.content || '';
          let parsedArgs = {};
          try {
            if (argsString) parsedArgs = JSON.parse(argsString);
          } catch { /* Incomplete JSON */ }

          streamingState.set(key, {
            toolName: event.tool || 'unknown',
            argsText: argsString,
            args: parsedArgs,
            status: 'streaming',
            step: event.step || 0,
          });
        } else if (event.type === 'action') {
          const key = `${event.tool}-${event.step || 0}`;
          streamingState.set(key, {
            toolName: event.tool || 'unknown',
            argsText: JSON.stringify(event.args || {}, null, 2),
            args: event.args || {},
            status: 'running',
            step: event.step || 0,
          });
        } else if (event.type === 'tool_call_block' && event.block) {
          const blockContent = event.block.content as any;
          const toolName = blockContent.tool_name || 'unknown';
          const toolNameLower = toolName.toLowerCase();
          // Remove streaming version when we get the persisted block (case-insensitive)
          for (const [k] of streamingState) {
            if (k.toLowerCase().startsWith(toolNameLower + '-')) {
              streamingState.delete(k);
              break;
            }
          }
        } else if (event.type === 'tool_result_block' && event.block) {
          // Results will be handled via toolBlocks
        }
      }
    }

    // Step 2: Build tool calls from persisted blocks (sorted by sequence_number)
    const toolCallsById = new Map<string, any>();
    const toolResultsById = new Map<string, ContentBlock>();

    if (toolBlocks.length > 0) {
      // First pass: collect all results
      for (const block of toolBlocks) {
        if (block.block_type === 'tool_result' && block.parent_block_id) {
          toolResultsById.set(block.parent_block_id, block);
        }
      }

      // Second pass: build tool calls with their results
      for (const block of toolBlocks) {
        if (block.block_type === 'tool_call') {
          const callContent = block.content as any;
          const result = toolResultsById.get(block.id);
          const resultContent = result?.content as any;
          const resultMetadata = result?.block_metadata as any;

          // Build result object that includes binary data if present
          let resultValue: any = resultContent?.result || resultContent?.error;

          // Check for binary data in content OR metadata (backend stores it in metadata)
          const isBinary = resultContent?.is_binary || resultMetadata?.is_binary;
          const binaryData = resultContent?.binary_data || resultMetadata?.image_data;
          const binaryType = resultContent?.binary_type || resultMetadata?.type;

          if (isBinary && binaryData) {
            resultValue = {
              is_binary: true,
              type: 'image',
              image_data: binaryData,
              binary_type: binaryType,
              text: resultContent?.result || '',
            };
          }

          toolCallsById.set(block.id, {
            toolCallId: block.id,
            toolName: callContent.tool_name || 'unknown',
            args: callContent.arguments || {},
            argsText: JSON.stringify(callContent.arguments || {}, null, 2),
            result: resultValue,
            isError: resultContent ? !resultContent.success : false,
            status: { type: result ? 'complete' : 'running' } as ToolCallMessagePartStatus,
            sequenceNumber: block.sequence_number,
            addResult: () => {},
            resume: () => {},
          });
        }
      }
    }

    // Step 3: Determine the correct order of text and tools
    // ReAct pattern: Thought (text) → Action (tool) → Observation (result)
    // So text typically comes BEFORE tools, unless the text block was CREATED after tools
    const fullText = textContent + streamingText;
    const textPart = fullText ? {
      type: 'text',
      content: fullText,
      isStreaming: isStreaming && (streamingText.length > 0 || streamEvents.length > 0),
    } : (isStreaming ? { type: 'text', content: '', isStreaming: true } : null);

    // Use created_at (not updated_at) to determine ordering
    // Text was created when the assistant started responding
    const textBlockCreatedAt = new Date(block.created_at).getTime();
    const toolCallBlocks = toolBlocks.filter(b => b.block_type === 'tool_call');
    const firstToolCallTime = toolCallBlocks.length > 0
      ? Math.min(...toolCallBlocks.map(b => new Date(b.created_at).getTime()))
      : Infinity;

    // Text comes after tools ONLY if the text block was created AFTER the first tool call
    // This handles the rare case where a summary text block is created after tools
    const showTextAfterTools = textBlockCreatedAt > firstToolCallTime
      && fullText.length > 0
      && !isStreaming;  // During streaming, keep current order

    // Sort persisted tools by sequence_number
    const sortedPersistedTools = Array.from(toolCallsById.values())
      .sort((a, b) => a.sequenceNumber - b.sequenceNumber);

    // Helper function to add tool parts
    const addToolParts = () => {
      for (const tool of sortedPersistedTools) {
        // Check if there's a streaming version with more recent state (case-insensitive)
        const toolNameLower = tool.toolName.toLowerCase();
        let streamingVersion = null;
        let streamingKey = null;
        for (const [key, state] of streamingState) {
          if (key.toLowerCase().startsWith(toolNameLower + '-')) {
            streamingVersion = state;
            streamingKey = key;
            break;
          }
        }

        if (streamingVersion && !tool.result) {
          // Tool is still streaming - use streaming state for args
          parts.push({
            type: 'tool-call',
            toolCallId: tool.toolCallId,
            toolName: tool.toolName,
            args: streamingVersion.args,
            argsText: streamingVersion.argsText,
            status: { type: streamingVersion.status === 'running' ? 'running' : 'running' },
            addResult: () => {},
            resume: () => {},
          });
          // Remove from streaming state since we've used it
          if (streamingKey) {
            streamingState.delete(streamingKey);
          }
        } else {
          // Use persisted state
          const { sequenceNumber, ...rest } = tool;
          parts.push({ type: 'tool-call', ...rest });
        }
      }

      // Add any remaining streaming-only tools (not yet persisted)
      for (const [key, state] of streamingState) {
        parts.push({
          type: 'tool-call',
          toolCallId: `streaming-${key}`,
          toolName: state.toolName,
          args: state.args,
          argsText: state.argsText,
          result: state.result,
          isError: state.isError,
          status: { type: state.status === 'complete' ? 'complete' : 'running' } as ToolCallMessagePartStatus,
          addResult: () => {},
          resume: () => {},
        });
      }
    };

    // Step 4: Add parts in the correct order based on timestamps
    if (showTextAfterTools) {
      // Tools first, then text (text is a summary after tool execution)
      addToolParts();
      if (textPart) parts.push(textPart);
    } else {
      // Text first, then tools (normal flow or streaming)
      if (textPart) parts.push(textPart);
      addToolParts();
    }

    return parts;
  }, [block.id, block.created_at, toolBlocks, isStreaming, streamEvents, textContent]);

  const renderPart = (part: any, index: number) => {
    if (part.type === 'text') {
      if (part.isStreaming) {
        return <StreamingText key={index} content={part.content} />;
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
      return <DefaultToolFallback key={part.toolCallId || index} {...part} />;
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
