import { useRef, useEffect, forwardRef, useState, useCallback } from 'react';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
import { MemoizedMessage } from './MemoizedMessage';
import { Message, StreamEvent } from '../hooks/useOptimizedStreaming';

interface VirtualizedChatListProps {
  messages: Message[];
  isStreaming: boolean;
  streamEvents?: StreamEvent[];
}

// Fix: Scroller component needs forwardRef for Virtuoso compatibility
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

// Item wrapper to center and constrain message width (matching old layout concept)
const ItemWrapper = ({ children }: { children: React.ReactNode }) => (
  <div style={{
    maxWidth: '48rem',
    margin: '0 auto',
    padding: '0 24px',
    width: '100%'
  }}>
    {children}
  </div>
);

export const VirtualizedChatList = ({ messages, isStreaming, streamEvents = [] }: VirtualizedChatListProps) => {
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const autoScrollingRef = useRef(false);

  // Detect when user manually scrolls
  const handleScroll = useCallback((isScrolling: boolean) => {
    // Only disable auto-scroll if:
    // 1. User is scrolling (isScrolling = true)
    // 2. Auto-scroll is currently enabled
    // 3. We're not programmatically scrolling (autoScrollingRef = false)
    if (isScrolling && autoScrollEnabled && !autoScrollingRef.current) {
      setAutoScrollEnabled(false);
    }
  }, [autoScrollEnabled]);

  // Detect if user is at bottom
  const handleAtBottomStateChange = useCallback((atBottom: boolean) => {
    setIsAtBottom(atBottom);
  }, []);

  // Auto-scroll to bottom when new message arrives OR during streaming (only if toggle is ON)
  useEffect(() => {
    if (messages.length > 0 && autoScrollEnabled) {
      // Mark that we're about to programmatically scroll
      autoScrollingRef.current = true;

      // Use setTimeout to ensure DOM has updated with new streaming content
      const timeoutId = setTimeout(() => {
        if (virtuosoRef.current) {
          // Scroll to the last message index for precise control
          virtuosoRef.current.scrollToIndex({
            index: messages.length - 1,
            align: 'end',
            behavior: isStreaming ? 'auto' : 'smooth',
          });
        }

        // Reset the flag after scrolling completes (with a delay to ensure scroll finishes)
        setTimeout(() => {
          autoScrollingRef.current = false;
        }, isStreaming ? 500 : 200);
      }, isStreaming ? 0 : 10);

      return () => {
        clearTimeout(timeoutId);
        autoScrollingRef.current = false;
      };
    }
  }, [messages.length, isStreaming, autoScrollEnabled, streamEvents]);

  return (
    <div style={{ position: 'relative', height: '100%', width: '100%' }}>
      <Virtuoso
        ref={virtuosoRef}
        data={messages}
        initialTopMostItemIndex={messages.length > 0 ? messages.length - 1 : 0}
        followOutput="auto"
        isScrolling={handleScroll}
        atBottomStateChange={handleAtBottomStateChange}
        itemContent={(index, message) => {
          const isLastMessage = index === messages.length - 1;
          const isCurrentlyStreaming = isStreaming && isLastMessage;

          return (
            <ItemWrapper>
              <MemoizedMessage
                key={message.id}
                message={message}
                isStreaming={isCurrentlyStreaming}
                streamEvents={isCurrentlyStreaming ? streamEvents : []}
              />
            </ItemWrapper>
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
        style={{ height: '100%', width: '100%' }}
      />

      {/* Auto-scroll toggle button */}
      <style>{`
        @keyframes scrollDown {
          0%, 100% {
            transform: translateY(0px);
            opacity: 1;
          }
          50% {
            transform: translateY(4px);
            opacity: 0.6;
          }
        }

        .auto-scroll-btn-animated svg {
          animation: scrollDown 1.5s ease-in-out infinite;
        }
      `}</style>
      <button
        onClick={() => setAutoScrollEnabled(!autoScrollEnabled)}
        className={autoScrollEnabled ? 'auto-scroll-btn-animated' : ''}
        style={{
          position: 'absolute',
          bottom: '20px',
          right: '20px',
          width: '44px',
          height: '44px',
          borderRadius: '50%',
          border: autoScrollEnabled ? 'none' : '2px solid #3b82f6',
          backgroundColor: autoScrollEnabled ? '#3b82f6' : 'white',
          color: autoScrollEnabled ? 'white' : '#3b82f6',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
          transition: 'all 0.2s ease',
          zIndex: 10,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'scale(1.05)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'scale(1)';
        }}
        title={autoScrollEnabled ? 'Auto-scroll enabled' : 'Auto-scroll disabled'}
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M10 4L10 16M10 16L6 12M10 16L14 12"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
};
