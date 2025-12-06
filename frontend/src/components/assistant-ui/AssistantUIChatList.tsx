/**
 * AssistantUIChatList - Virtualized chat list using assistant-ui components
 *
 * This component provides virtualized rendering with assistant-ui message components
 * for optimal performance with large message histories.
 *
 * Uses Virtuoso's built-in followOutput behavior for smooth auto-scrolling:
 * - followOutput="smooth" handles new content scrolling automatically
 * - atBottomStateChange tracks when user scrolls away from bottom
 * - No manual scroll effects needed - let Virtuoso handle it
 *
 * Now works with ContentBlocks instead of Messages.
 */

import { useRef, forwardRef, memo, useCallback, useMemo } from 'react';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
import { AssistantUIMessage } from './AssistantUIMessage';
import './AssistantUIChat.css';
import { ContentBlock, StreamEvent } from "@/types";

interface AssistantUIChatListProps {
  blocks: ContentBlock[];
  isStreaming: boolean;
  streamEvents?: StreamEvent[];
}

// Custom scroller with thin scrollbar
const CustomScroller = forwardRef<HTMLDivElement, any>(({ style, ...props }, ref) => (
  <div
    ref={ref}
    {...props}
    style={{
      ...style,
      scrollbarWidth: 'thin',
      scrollbarColor: '#cbd5e0 transparent',
    }}
  />
));
CustomScroller.displayName = 'CustomScroller';

// Memoized message component for performance
const MemoizedAssistantUIMessage = memo(AssistantUIMessage, (prevProps, nextProps) => {
  // Only re-render if essential properties change
  return (
    prevProps.block.id === nextProps.block.id &&
    prevProps.block.content?.text === nextProps.block.content?.text &&
    prevProps.isStreaming === nextProps.isStreaming &&
    prevProps.streamEvents?.length === nextProps.streamEvents?.length &&
    prevProps.toolBlocks?.length === nextProps.toolBlocks?.length
  );
});

/**
 * Group content blocks into display groups:
 * - user_text blocks become individual items
 * - assistant_text blocks with their associated tool_call and tool_result blocks become a single group
 */
interface DisplayGroup {
  type: 'user' | 'assistant';
  mainBlock: ContentBlock;
  toolBlocks: ContentBlock[];  // tool_call and tool_result blocks associated with this assistant response
}

function groupBlocks(blocks: ContentBlock[]): DisplayGroup[] {
  const groups: DisplayGroup[] = [];
  let currentAssistantGroup: DisplayGroup | null = null;

  // Sort by sequence_number to ensure correct order
  const sortedBlocks = [...blocks].sort((a, b) => a.sequence_number - b.sequence_number);

  for (const block of sortedBlocks) {
    if (block.block_type === 'user_text') {
      // Flush any pending assistant group
      if (currentAssistantGroup) {
        groups.push(currentAssistantGroup);
        currentAssistantGroup = null;
      }
      groups.push({
        type: 'user',
        mainBlock: block,
        toolBlocks: [],
      });
    } else if (block.block_type === 'assistant_text') {
      // Flush any pending assistant group
      if (currentAssistantGroup) {
        groups.push(currentAssistantGroup);
      }
      // Start new assistant group
      currentAssistantGroup = {
        type: 'assistant',
        mainBlock: block,
        toolBlocks: [],
      };
    } else if (block.block_type === 'tool_call' || block.block_type === 'tool_result') {
      // Add to current assistant group if exists
      if (currentAssistantGroup) {
        currentAssistantGroup.toolBlocks.push(block);
      } else {
        // Orphan tool block - create a placeholder assistant group
        currentAssistantGroup = {
          type: 'assistant',
          mainBlock: {
            id: `placeholder-${block.id}`,
            chat_session_id: block.chat_session_id,
            sequence_number: block.sequence_number - 1,
            block_type: 'assistant_text',
            author: 'assistant',
            content: { text: '' },
            block_metadata: {},
            created_at: block.created_at,
            updated_at: block.updated_at,
          },
          toolBlocks: [block],
        };
      }
    } else if (block.block_type === 'system') {
      // System blocks can be shown as assistant messages
      if (currentAssistantGroup) {
        groups.push(currentAssistantGroup);
        currentAssistantGroup = null;
      }
      groups.push({
        type: 'assistant',
        mainBlock: block,
        toolBlocks: [],
      });
    }
  }

  // Flush final assistant group
  if (currentAssistantGroup) {
    groups.push(currentAssistantGroup);
  }

  return groups;
}

export const AssistantUIChatList: React.FC<AssistantUIChatListProps> = ({
  blocks,
  isStreaming,
  streamEvents = [],
}) => {
  const virtuosoRef = useRef<VirtuosoHandle>(null);

  // Group blocks into display units
  const displayGroups = useMemo(() => groupBlocks(blocks), [blocks]);

  // followOutput as a function - Virtuoso calls this when new items are added
  // Returns 'smooth' to auto-scroll, or false to stay in place
  // This is Virtuoso's recommended approach for auto-scroll behavior
  const handleFollowOutput = useCallback((isAtBottom: boolean) => {
    // During streaming, use 'auto' for instant scroll (no animation delay)
    // Otherwise use 'smooth' for nice animation when new messages arrive
    if (isAtBottom) {
      return isStreaming ? 'auto' : 'smooth';
    }
    return false;
  }, [isStreaming]);

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <Virtuoso
        ref={virtuosoRef}
        data={displayGroups}
        initialTopMostItemIndex={displayGroups.length > 0 ? displayGroups.length - 1 : 0}
        followOutput={handleFollowOutput}
        atBottomThreshold={100}
        itemContent={(index, group) => {
          const isLastGroup = index === displayGroups.length - 1;
          const isCurrentlyStreaming = isStreaming && isLastGroup && group.type === 'assistant';

          return (
            <MemoizedAssistantUIMessage
              key={group.mainBlock.id}
              block={group.mainBlock}
              toolBlocks={group.toolBlocks}
              isStreaming={isCurrentlyStreaming}
              streamEvents={isCurrentlyStreaming ? streamEvents : []}
            />
          );
        }}
        components={{
          Scroller: CustomScroller,
          Footer: () => <div style={{ height: '80px' }} />,
          EmptyPlaceholder: () => (
            <div className="empty-chat">
              <h3>Start a conversation</h3>
              <p>Ask me anything, and I'll help you with code, data analysis, and more.</p>
            </div>
          ),
        }}
        style={{ height: '100%' }}
      />
    </div>
  );
};
