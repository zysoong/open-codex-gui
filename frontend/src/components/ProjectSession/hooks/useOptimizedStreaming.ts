import { useState, useRef, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ContentBlock, StreamEvent } from "@/types";

// Industry standard: 30ms interval = 33 updates/second (ChatGPT-like speed)
const FLUSH_INTERVAL_MS = 30;

interface UseOptimizedStreamingProps {
  sessionId: string;
  initialBlocks?: ContentBlock[];
}

interface UseOptimizedStreamingReturn {
  blocks: ContentBlock[];
  streamEvents: StreamEvent[];
  isStreaming: boolean;
  error: string | null;
  sendMessage: (content: string) => boolean;
  cancelStream: () => void;
  clearError: () => void;
  isWebSocketReady: boolean;
}

// Per-block streaming state
interface BlockStreamState {
  blockId: string;
  bufferedContent: string;
  streaming: boolean;
}

export const useOptimizedStreaming = ({
  sessionId,
  initialBlocks = []
}: UseOptimizedStreamingProps): UseOptimizedStreamingReturn => {
  const [blocks, setBlocks] = useState<ContentBlock[]>(initialBlocks);
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();

  // NEW: Per-block stream state map (replaces single ref)
  const streamStatesRef = useRef<Map<string, BlockStreamState>>(new Map());

  // Track active streaming block (for events without block_id - legacy fallback)
  const activeBlockIdRef = useRef<string | null>(null);

  // Buffer for stream events (tool calls, etc.)
  const eventBufferRef = useRef<StreamEvent[]>([]);

  // Optimized: 30ms interval for ChatGPT-like streaming speed
  // Now flushes per-block instead of global buffer
  useEffect(() => {
    if (!isStreaming) return;

    const flushInterval = setInterval(() => {
      // Flush each block's buffered content
      streamStatesRef.current.forEach((state, blockId) => {
        if (state.bufferedContent) {
          setBlocks(prev => {
            const updated = [...prev];
            const targetIndex = updated.findIndex(b => b.id === blockId);

            if (targetIndex !== -1) {
              const currentText = updated[targetIndex].content?.text || '';
              updated[targetIndex] = {
                ...updated[targetIndex],
                content: { text: currentText + state.bufferedContent }
              };
            }

            return updated;
          });

          // Clear this block's buffer after flushing
          state.bufferedContent = '';
        }
      });

      // Flush stream events
      if (eventBufferRef.current.length > 0) {
        setStreamEvents(prev => [...prev, ...eventBufferRef.current]);
        eventBufferRef.current = [];
      }
    }, FLUSH_INTERVAL_MS);

    return () => clearInterval(flushInterval);
  }, [isStreaming]);

  // WebSocket message handler
  const handleWebSocketMessage = useCallback((event: MessageEvent) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'stream_sync':
        // NEW: Server sends full stream state for reconnection
        console.log('[WS] stream_sync:', data.block_id, 'content length:', data.accumulated_content?.length);

        // Initialize stream state for this block
        streamStatesRef.current.set(data.block_id, {
          blockId: data.block_id,
          bufferedContent: '',
          streaming: true
        });
        activeBlockIdRef.current = data.block_id;

        // Update or create the block with synced content (server is source of truth)
        setBlocks(prev => {
          const existingIndex = prev.findIndex(b => b.id === data.block_id);

          if (existingIndex !== -1) {
            // Replace existing block's content with server state
            const updated = [...prev];
            updated[existingIndex] = {
              ...updated[existingIndex],
              content: { text: data.accumulated_content || '' },
              block_metadata: { streaming: true }
            };
            return updated;
          } else {
            // Create new block with synced content
            return [
              ...prev,
              {
                id: data.block_id,
                chat_session_id: sessionId,
                sequence_number: data.sequence_number || 0,
                block_type: 'assistant_text',
                author: 'assistant',
                content: { text: data.accumulated_content || '' },
                block_metadata: { streaming: true },
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              } as ContentBlock
            ];
          }
        });

        setIsStreaming(true);
        setError(null);
        break;

      case 'user_text_block':
        // User message received confirmation from server
        console.log('[WS] user_text_block:', data.block?.id);
        if (data.block) {
          setBlocks(prev => {
            // Replace temp user block with server block or add new
            const tempIndex = prev.findIndex(b => b.id.startsWith('temp-user-'));
            if (tempIndex !== -1) {
              const updated = [...prev];
              updated[tempIndex] = data.block;
              return updated;
            }
            return [...prev, data.block];
          });
        }
        break;

      case 'assistant_text_start':
        // Assistant started streaming
        console.log('[WS] assistant_text_start:', data.block_id);
        setIsStreaming(true);
        setError(null);
        setStreamEvents([]);
        eventBufferRef.current = [];

        // Initialize stream state for this block
        streamStatesRef.current.set(data.block_id, {
          blockId: data.block_id,
          bufferedContent: '',
          streaming: true
        });
        activeBlockIdRef.current = data.block_id;

        // Add new assistant_text block
        setBlocks(prev => [
          ...prev,
          {
            id: data.block_id,
            chat_session_id: sessionId,
            sequence_number: data.sequence_number || 0,
            block_type: 'assistant_text',
            author: 'assistant',
            content: { text: '' },
            block_metadata: { streaming: true },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          } as ContentBlock
        ]);
        break;

      case 'chunk':
        // Text chunk from assistant - NOW WITH BLOCK_ID
        const chunkBlockId = data.block_id || activeBlockIdRef.current;

        if (chunkBlockId) {
          // Get or create stream state for this block
          let state = streamStatesRef.current.get(chunkBlockId);
          if (!state) {
            state = {
              blockId: chunkBlockId,
              bufferedContent: '',
              streaming: true
            };
            streamStatesRef.current.set(chunkBlockId, state);
          }

          // Append to this block's buffer
          state.bufferedContent += data.content || '';
        } else {
          console.warn('[WS] chunk without block_id and no active block');
        }
        break;

      case 'action_streaming':
        // Real-time feedback when tool name is first received
        eventBufferRef.current.push({
          type: 'action_streaming',
          content: `Preparing ${data.tool}...`,
          tool: data.tool,
          status: data.status,
          step: data.step,
        });
        break;

      case 'action_args_chunk':
        // Streaming tool arguments
        eventBufferRef.current.push({
          type: 'action_args_chunk',
          content: data.partial_args || '',
          tool: data.tool,
          partial_args: data.partial_args,
          step: data.step,
        });
        break;

      case 'action':
        // Complete tool call
        setStreamEvents(prev =>
          prev.filter(e => !(e.type === 'action_args_chunk' && e.tool === data.tool))
        );
        eventBufferRef.current.push({
          type: 'action',
          content: `Using tool: ${data.tool}`,
          tool: data.tool,
          args: data.args,
          step: data.step,
        });
        break;

      case 'tool_call_block':
        // Tool call block received
        console.log('[WS] tool_call_block:', data.block?.id);
        if (data.block) {
          setBlocks(prev => [...prev, data.block]);
          eventBufferRef.current.push({
            type: 'tool_call_block',
            block: data.block,
          });
        }
        break;

      case 'tool_result_block':
        // Tool result block received
        console.log('[WS] tool_result_block:', data.block?.id);
        if (data.block) {
          setBlocks(prev => [...prev, data.block]);
          eventBufferRef.current.push({
            type: 'tool_result_block',
            block: data.block,
          });
        }
        break;

      case 'assistant_text_end':
        // Assistant finished streaming
        console.log('[WS] assistant_text_end:', data.block_id);
        const endBlockId = data.block_id;

        // Final flush of any remaining content for this block
        if (endBlockId) {
          const state = streamStatesRef.current.get(endBlockId);
          if (state && state.bufferedContent) {
            setBlocks(prev => {
              const updated = [...prev];
              const targetIndex = updated.findIndex(b => b.id === endBlockId);

              if (targetIndex !== -1) {
                const currentText = updated[targetIndex].content?.text || '';
                updated[targetIndex] = {
                  ...updated[targetIndex],
                  content: { text: currentText + state.bufferedContent },
                  block_metadata: { streaming: false }
                };
              }

              return updated;
            });
          }

          // Clear stream state for this block
          streamStatesRef.current.delete(endBlockId);

          // If this was the active block, clear it
          if (activeBlockIdRef.current === endBlockId) {
            activeBlockIdRef.current = null;
          }
        }

        // Flush remaining events
        if (eventBufferRef.current.length > 0) {
          setStreamEvents(prev => [...prev, ...eventBufferRef.current]);
          eventBufferRef.current = [];
        }

        // Check if any blocks are still streaming
        const stillStreaming = Array.from(streamStatesRef.current.values())
          .some(s => s.streaming);

        if (!stillStreaming) {
          setIsStreaming(false);
          setStreamEvents([]);
        }

        // Refetch blocks from API to get persisted version
        queryClient.invalidateQueries({ queryKey: ['contentBlocks', sessionId] });
        break;

      case 'end':
        // Legacy end event
        console.log('[WS] end event received');
        streamStatesRef.current.clear();
        activeBlockIdRef.current = null;
        eventBufferRef.current = [];
        setIsStreaming(false);
        setStreamEvents([]);
        queryClient.invalidateQueries({ queryKey: ['contentBlocks', sessionId] });
        break;

      case 'cancelled':
        console.log('[WS] cancelled event');
        // Flush remaining content for all streaming blocks
        streamStatesRef.current.forEach((state, blockId) => {
          if (state.bufferedContent) {
            setBlocks(prev => {
              const updated = [...prev];
              const targetIndex = updated.findIndex(b => b.id === blockId);

              if (targetIndex !== -1) {
                const currentText = updated[targetIndex].content?.text || '';
                updated[targetIndex] = {
                  ...updated[targetIndex],
                  content: { text: currentText + state.bufferedContent },
                  block_metadata: { streaming: false, cancelled: true }
                };
              }

              return updated;
            });
          }
        });

        streamStatesRef.current.clear();
        activeBlockIdRef.current = null;
        eventBufferRef.current = [];
        setIsStreaming(false);
        break;

      case 'error':
        console.error('WebSocket error:', data.content || data.message);
        const errorMessage = data.content || data.message || 'An error occurred';

        if (!errorMessage.includes('No active task found')) {
          setError(errorMessage);
        }

        // Flush any remaining content
        streamStatesRef.current.forEach((state, blockId) => {
          if (state.bufferedContent) {
            setBlocks(prev => {
              const updated = [...prev];
              const targetIndex = updated.findIndex(b => b.id === blockId);

              if (targetIndex !== -1) {
                const currentText = updated[targetIndex].content?.text || '';
                updated[targetIndex] = {
                  ...updated[targetIndex],
                  content: { text: currentText + state.bufferedContent }
                };
              }

              return updated;
            });
          }
        });

        streamStatesRef.current.clear();
        activeBlockIdRef.current = null;
        eventBufferRef.current = [];
        setIsStreaming(false);
        break;

      case 'title_updated':
        console.log('[TITLE] Session title updated:', data.title);
        queryClient.invalidateQueries({ queryKey: ['chatSessions'] });
        queryClient.invalidateQueries({ queryKey: ['chatSession', sessionId] });
        break;

      case 'heartbeat':
        // Heartbeat message to keep connection alive
        break;

      case 'resuming_stream':
        // Legacy reconnection event (fallback when stream_sync not available)
        console.log('[WS] resuming_stream (legacy):', data.message_id);
        setError(null);
        setStreamEvents([]);
        eventBufferRef.current = [];

        const resumedBlockId = data.message_id || 'temp-resumed-' + Date.now();

        // Initialize stream state
        streamStatesRef.current.set(resumedBlockId, {
          blockId: resumedBlockId,
          bufferedContent: '',
          streaming: true
        });
        activeBlockIdRef.current = resumedBlockId;

        setBlocks(prev => {
          const existingBlock = prev.find(b => b.id === data.message_id);
          if (existingBlock) {
            // Mark existing block as streaming again
            return prev.map(b =>
              b.id === data.message_id
                ? { ...b, block_metadata: { ...b.block_metadata, streaming: true } }
                : b
            );
          }

          // Create new block if not found
          return [
            ...prev,
            {
              id: resumedBlockId,
              chat_session_id: sessionId,
              sequence_number: 0,
              block_type: 'assistant_text',
              author: 'assistant',
              content: { text: '' },
              block_metadata: { streaming: true },
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            } as ContentBlock
          ];
        });

        setIsStreaming(true);
        break;

      case 'start':
        // Legacy start event
        setIsStreaming(true);
        setError(null);
        setStreamEvents([]);
        eventBufferRef.current = [];

        const messageId = data.message_id || 'temp-' + Date.now();
        streamStatesRef.current.set(messageId, {
          blockId: messageId,
          bufferedContent: '',
          streaming: true
        });
        activeBlockIdRef.current = messageId;

        setBlocks(prev => [
          ...prev,
          {
            id: messageId,
            chat_session_id: sessionId,
            sequence_number: prev.length,
            block_type: 'assistant_text',
            author: 'assistant',
            content: { text: '' },
            block_metadata: { streaming: true },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          } as ContentBlock
        ]);
        break;

      case 'observation':
        // Legacy observation event
        eventBufferRef.current.push({
          type: 'tool_result_block',
          content: data.content,
          success: data.success,
          metadata: data.metadata,
          step: data.step,
        });
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

    return () => {
      console.log('[useOptimizedStreaming] Cleaning up WebSocket');
      ws.close();
    };
  }, [sessionId, handleWebSocketMessage]);

  // Update blocks when external data changes
  useEffect(() => {
    if (initialBlocks && initialBlocks.length > 0) {
      setBlocks(initialBlocks);
    }
  }, [initialBlocks]);

  // Send message via WebSocket
  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error('[useOptimizedStreaming] WebSocket not ready');
      return false;
    }

    if (!content.trim()) {
      return false;
    }

    // Add temp user block to local state immediately
    const tempUserBlock: ContentBlock = {
      id: 'temp-user-' + Date.now(),
      chat_session_id: sessionId,
      sequence_number: blocks.length,
      block_type: 'user_text',
      author: 'user',
      content: { text: content },
      block_metadata: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    setBlocks(prev => [...prev, tempUserBlock]);

    // Send via WebSocket
    wsRef.current.send(JSON.stringify({
      type: 'message',
      content,
    }));

    return true;
  }, [sessionId, blocks.length]);

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
    blocks,
    streamEvents,
    isStreaming,
    error,
    sendMessage,
    cancelStream,
    clearError,
    isWebSocketReady: wsRef.current?.readyState === WebSocket.OPEN,
  };
};
