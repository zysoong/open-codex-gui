import { useState, useRef, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

// Industry standard: 30ms interval = 33 updates/second (ChatGPT-like speed)
const FLUSH_INTERVAL_MS = 30;

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  agent_actions?: any[];
}

export interface StreamEvent {
  type: 'chunk' | 'action' | 'action_streaming' | 'action_args_chunk' | 'observation';
  content?: string;
  tool?: string;
  args?: any;
  partial_args?: string;
  step?: number;
  success?: boolean;
  status?: string;
  metadata?: any;
}

interface UseOptimizedStreamingProps {
  sessionId: string | undefined;
  initialMessages?: Message[];
}

export const useOptimizedStreaming = ({ sessionId, initialMessages = [] }: UseOptimizedStreamingProps) => {
  // Initialize with empty array - we'll update from initialMessages in useEffect
  // This prevents messages from disappearing when component remounts during streaming
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasInitializedRef = useRef(false);

  const wsRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();

  // Buffers for batching (no re-renders when updated)
  const chunkBufferRef = useRef<string>('');
  const eventBufferRef = useRef<StreamEvent[]>([]);

  // Optimized: 30ms interval for ChatGPT-like streaming speed
  useEffect(() => {
    if (!isStreaming) return;

    const flushInterval = setInterval(() => {
      const bufferedContent = chunkBufferRef.current;
      const bufferedEvents = eventBufferRef.current;

      if (!bufferedContent && bufferedEvents.length === 0) {
        return; // Nothing to flush
      }

      // Flush messages
      if (bufferedContent) {
        setMessages(prev => {
          const updated = [...prev];
          const lastMessage = updated[updated.length - 1];

          if (lastMessage && lastMessage.role === 'assistant') {
            // Immutable update
            updated[updated.length - 1] = {
              ...lastMessage,
              content: lastMessage.content + bufferedContent
            };
          }

          return updated;
        });
      }

      // Flush stream events
      if (bufferedEvents.length > 0) {
        setStreamEvents(prev => [...prev, ...bufferedEvents]);
      }

      // Clear buffers after flush
      chunkBufferRef.current = '';
      eventBufferRef.current = [];
    }, FLUSH_INTERVAL_MS);

    return () => clearInterval(flushInterval);
  }, [isStreaming]);

  // WebSocket message handler
  const handleWebSocketMessage = useCallback((event: MessageEvent) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'start':
        setIsStreaming(true);
        setError(null);
        // Clear buffers for new streaming session
        chunkBufferRef.current = '';
        eventBufferRef.current = [];
        setStreamEvents([]);

        // Add new assistant message
        setMessages(prev => [
          ...prev,
          {
            id: 'temp-' + Date.now(),
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
          }
        ]);
        break;

      case 'chunk':
        // Just accumulate in buffer - interval will flush
        chunkBufferRef.current += data.content;
        eventBufferRef.current.push({
          type: 'chunk',
          content: data.content,
        });
        break;

      case 'action_streaming':
        eventBufferRef.current.push({
          type: 'action_streaming',
          content: `Preparing ${data.tool}...`,
          tool: data.tool,
          status: data.status,
          step: data.step,
        });
        break;

      case 'action_args_chunk':
        // Display argument chunks immediately for real-time streaming (📝 emoji)
        // This makes file_edit, file_write, etc. show progress as LLM generates args
        setStreamEvents(prev => [...prev, {
          type: 'action_args_chunk',
          content: data.partial_args || '',
          tool: data.tool,
          partial_args: data.partial_args,
          step: data.step,
        }]);
        break;

      case 'action':
        // Remove all action_args_chunk events for this tool from existing state
        // This prevents retroactive filtering during render
        // Then immediately add the action event (not buffered) for instant display
        setStreamEvents(prev => [
          ...prev.filter(e => !(e.type === 'action_args_chunk' && e.tool === data.tool)),
          {
            type: 'action',
            content: `Using tool: ${data.tool}`,
            tool: data.tool,
            args: data.args,
            step: data.step,
          }
        ]);
        break;

      case 'observation':
        // Observations should be displayed immediately, not buffered
        // This ensures file_edit and other tool results appear in real-time
        setStreamEvents(prev => [...prev, {
          type: 'observation',
          content: data.content,
          success: data.success,
          metadata: data.metadata,
          step: data.step,
        }]);
        break;

      case 'end':
        // Final flush of any remaining buffered content
        const finalContent = chunkBufferRef.current;
        const finalEvents = eventBufferRef.current;

        if (finalContent) {
          setMessages(prev => {
            const updated = [...prev];
            const lastMessage = updated[updated.length - 1];

            if (lastMessage && lastMessage.role === 'assistant') {
              updated[updated.length - 1] = {
                ...lastMessage,
                content: lastMessage.content + finalContent
              };
            }

            return updated;
          });
        }

        if (finalEvents.length > 0) {
          setStreamEvents(prev => [...prev, ...finalEvents]);
        }

        // Clear buffers
        chunkBufferRef.current = '';
        eventBufferRef.current = [];

        // Stop streaming
        setIsStreaming(false);
        setStreamEvents([]);

        // Refetch messages from API to get persisted version
        queryClient.invalidateQueries({ queryKey: ['messages', sessionId] });
        break;

      case 'cancelled':
        // Flush remaining content
        if (chunkBufferRef.current) {
          setMessages(prev => {
            const updated = [...prev];
            const lastMessage = updated[updated.length - 1];

            if (lastMessage && lastMessage.role === 'assistant') {
              updated[updated.length - 1] = {
                ...lastMessage,
                content: lastMessage.content + chunkBufferRef.current
              };
            }

            return updated;
          });
        }

        chunkBufferRef.current = '';
        eventBufferRef.current = [];
        setIsStreaming(false);
        break;

      case 'error':
        console.error('WebSocket error:', data.content);
        setError(data.content || 'An error occurred');
        setIsStreaming(false);
        // Flush any pending content
        if (chunkBufferRef.current) {
          setMessages(prev => {
            const updated = [...prev];
            const lastMessage = updated[updated.length - 1];

            if (lastMessage && lastMessage.role === 'assistant') {
              updated[updated.length - 1] = {
                ...lastMessage,
                content: lastMessage.content + chunkBufferRef.current
              };
            }

            return updated;
          });
        }
        chunkBufferRef.current = '';
        eventBufferRef.current = [];
        break;

      case 'title_updated':
        console.log('[TITLE] Session title updated:', data.title);
        // Invalidate chat sessions query to refresh sidebar with new title
        queryClient.invalidateQueries({ queryKey: ['chatSessions'] });
        // Invalidate current session query to refresh header title
        queryClient.invalidateQueries({ queryKey: ['chatSession', sessionId] });
        break;

      default:
        console.warn('Unknown WebSocket message type:', data.type);
    }
  }, [sessionId, queryClient]);

  // WebSocket connection setup
  useEffect(() => {
    if (!sessionId) return;

    const ws = new WebSocket(`ws://127.0.0.1:8000/api/v1/chats/${sessionId}/stream`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[useOptimizedStreaming] WebSocket connected');
    };

    ws.onmessage = handleWebSocketMessage;

    ws.onerror = (error) => {
      console.error('[useOptimizedStreaming] WebSocket error:', error);
      setIsStreaming(false);
      setError('Connection error occurred');
    };

    ws.onclose = () => {
      console.log('[useOptimizedStreaming] WebSocket closed');
      setIsStreaming(false);
    };

    // Cleanup on unmount
    return () => {
      console.log('[useOptimizedStreaming] Cleaning up WebSocket');
      ws.close();
    };
  }, [sessionId, handleWebSocketMessage]);

  // Update messages when external data changes
  // This handles both initial load and updates when navigating back to the chat
  useEffect(() => {
    if (initialMessages && initialMessages.length > 0) {
      // On first mount, always set messages from initialMessages
      if (!hasInitializedRef.current) {
        setMessages(initialMessages);
        hasInitializedRef.current = true;
        return;
      }

      // On subsequent updates, only update if we have more messages than before
      // This prevents messages from disappearing when navigating back during streaming
      setMessages(prev => {
        if (prev.length > 0 && initialMessages.length <= prev.length) {
          return prev;
        }
        return initialMessages;
      });
    }
  }, [initialMessages]);

  // Send message via WebSocket
  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error('[useOptimizedStreaming] WebSocket not ready');
      return false;
    }

    if (!content.trim()) {
      return false;
    }

    // Add user message to local state immediately
    const userMessage: Message = {
      id: 'temp-user-' + Date.now(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);

    // Send via WebSocket
    wsRef.current.send(JSON.stringify({
      type: 'message',
      content,
    }));

    return true;
  }, []);

  // Cancel streaming
  const cancelStream = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'cancel' }));
    }
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    messages,
    streamEvents,
    isStreaming,
    error,
    sendMessage,
    cancelStream,
    clearError,
    isWebSocketReady: wsRef.current?.readyState === WebSocket.OPEN,
  };
};
