import { useState, useRef, useCallback, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

const BATCH_FLUSH_INTERVAL = 16; // ~60fps

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  agent_actions?: any[];
}

export interface StreamEvent {
  type: 'chunk' | 'thought' | 'action' | 'action_streaming' | 'action_args_chunk' | 'observation';
  content?: string;
  tool?: string;
  args?: any;
  partial_args?: string;
  step?: number;
  success?: boolean;
  status?: string;
}

interface UseStreamingManagerProps {
  sessionId: string | undefined;
  initialMessages?: Message[];
}

export const useStreamingManager = ({ sessionId, initialMessages = [] }: UseStreamingManagerProps) => {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();

  // Batching refs for chunk optimization
  const chunkBufferRef = useRef<string>('');
  const eventBufferRef = useRef<StreamEvent[]>([]);
  const rafIdRef = useRef<number | null>(null);

  // Flush buffered chunks to state (batched at 60fps)
  const flushBufferedUpdates = useCallback(() => {
    rafIdRef.current = null;

    const bufferedContent = chunkBufferRef.current;
    const bufferedEvents = eventBufferRef.current;

    if (!bufferedContent && bufferedEvents.length === 0) {
      return;
    }

    // Single batched state update for messages
    if (bufferedContent) {
      setMessages(prev => {
        const updated = [...prev];
        const lastMessage = updated[updated.length - 1];

        if (lastMessage && lastMessage.role === 'assistant') {
          // Immutable update - create new message object
          updated[updated.length - 1] = {
            ...lastMessage,
            content: lastMessage.content + bufferedContent
          };
        }

        return updated;
      });
    }

    // Single batched state update for stream events
    if (bufferedEvents.length > 0) {
      setStreamEvents(prev => [...prev, ...bufferedEvents]);
    }

    // Clear buffers
    chunkBufferRef.current = '';
    eventBufferRef.current = [];
  }, []);

  // Schedule a batched flush on next animation frame
  const scheduleBatchedFlush = useCallback(() => {
    if (rafIdRef.current === null) {
      rafIdRef.current = requestAnimationFrame(flushBufferedUpdates);
    }
  }, [flushBufferedUpdates]);

  // Force immediate flush (for 'end' event)
  const forceFlush = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    flushBufferedUpdates();
  }, [flushBufferedUpdates]);

  // Clear all buffers (for 'start' event)
  const clearBuffers = useCallback(() => {
    chunkBufferRef.current = '';
    eventBufferRef.current = [];
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  // WebSocket message handler
  const handleWebSocketMessage = useCallback((event: MessageEvent) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'start':
        setIsStreaming(true);
        setError(null);
        clearBuffers();
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
        // Buffer chunk instead of immediate update
        chunkBufferRef.current += data.content;
        eventBufferRef.current.push({
          type: 'chunk',
          content: data.content,
        });
        scheduleBatchedFlush();
        break;

      case 'thought':
        eventBufferRef.current.push({
          type: 'thought',
          content: data.content,
          step: data.step,
        });
        scheduleBatchedFlush();
        break;

      case 'action_streaming':
        eventBufferRef.current.push({
          type: 'action_streaming',
          content: `Preparing ${data.tool}...`,
          tool: data.tool,
          status: data.status,
          step: data.step,
        });
        scheduleBatchedFlush();
        break;

      case 'action_args_chunk':
        eventBufferRef.current.push({
          type: 'action_args_chunk',
          content: data.partial_args || '',
          tool: data.tool,
          partial_args: data.partial_args,
          step: data.step,
        });
        scheduleBatchedFlush();
        break;

      case 'action':
        eventBufferRef.current.push({
          type: 'action',
          content: `Using tool: ${data.tool}`,
          tool: data.tool,
          args: data.args,
          step: data.step,
        });
        scheduleBatchedFlush();
        break;

      case 'observation':
        eventBufferRef.current.push({
          type: 'observation',
          content: data.content,
          success: data.success,
          step: data.step,
        });
        scheduleBatchedFlush();
        break;

      case 'end':
        // Force flush any remaining chunks immediately
        forceFlush();
        setIsStreaming(false);
        setStreamEvents([]);

        // Refetch messages from API to get persisted version
        queryClient.invalidateQueries({ queryKey: ['messages', sessionId] });
        break;

      case 'cancelled':
        forceFlush();
        setIsStreaming(false);
        break;

      case 'error':
        console.error('WebSocket error:', data.content);
        setError(data.content || 'An error occurred');
        setIsStreaming(false);
        forceFlush();
        break;

      default:
        console.warn('Unknown WebSocket message type:', data.type);
    }
  }, [sessionId, scheduleBatchedFlush, forceFlush, clearBuffers, queryClient]);

  // WebSocket connection setup
  useEffect(() => {
    if (!sessionId) return;

    const ws = new WebSocket(`ws://127.0.0.1:8000/api/v1/chats/${sessionId}/stream`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[useStreamingManager] WebSocket connected');
    };

    ws.onmessage = handleWebSocketMessage;

    ws.onerror = (error) => {
      console.error('[useStreamingManager] WebSocket error:', error);
      setIsStreaming(false);
      setError('Connection error occurred');
    };

    ws.onclose = () => {
      console.log('[useStreamingManager] WebSocket closed');
      setIsStreaming(false);
    };

    // Cleanup on unmount
    return () => {
      console.log('[useStreamingManager] Cleaning up WebSocket');
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
      }
      ws.close();
    };
  }, [sessionId, handleWebSocketMessage]);

  // Update messages when external data changes
  useEffect(() => {
    if (initialMessages && initialMessages.length > 0) {
      setMessages(initialMessages);
    }
  }, [initialMessages]);

  // Send message via WebSocket
  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error('[useStreamingManager] WebSocket not ready');
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
