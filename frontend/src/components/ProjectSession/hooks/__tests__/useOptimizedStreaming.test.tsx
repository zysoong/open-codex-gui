import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useOptimizedStreaming } from '../useOptimizedStreaming';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React, { ReactNode } from 'react';

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  url: string;
  onopen: ((event: any) => void) | null = null;
  onmessage: ((event: any) => void) | null = null;
  onerror: ((event: any) => void) | null = null;
  onclose: ((event: any) => void) | null = null;

  sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    // Simulate connection opening
    setTimeout(() => {
      if (this.onopen) {
        this.onopen(new Event('open'));
      }
    }, 0);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new Event('close'));
    }
  }

  // Helper method to simulate receiving messages
  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  // Helper method to simulate errors
  simulateError(error: any) {
    if (this.onerror) {
      this.onerror(error);
    }
  }
}

describe('useOptimizedStreaming', () => {
  let mockWs: MockWebSocket;
  let queryClient: QueryClient;
  let wsInstances: MockWebSocket[] = [];

  beforeEach(() => {
    // Clear instances array
    wsInstances = [];

    // Mock WebSocket globally with vi.fn() to track instantiations
    global.WebSocket = vi.fn().mockImplementation((url: string) => {
      const instance = new MockWebSocket(url);
      wsInstances.push(instance);
      return instance;
    }) as any;

    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  // Create wrapper function that uses current queryClient instance
  const getWrapper = () => ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  describe('initialization', () => {
    it('should initialize with default values', () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      expect(result.current.messages).toEqual([]);
      expect(result.current.streamEvents).toEqual([]);
      expect(result.current.isStreaming).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it('should initialize with initial messages', () => {
      const initialMessages = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'Hello',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session', initialMessages }),
        { wrapper: getWrapper() }
      );

      expect(result.current.messages).toEqual(initialMessages);
    });

    it('should establish WebSocket connection', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.isWebSocketReady).toBe(true);
    });

    it('should not connect without sessionId', () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: undefined }),
        { wrapper: getWrapper() }
      );

      expect(result.current.isWebSocketReady).toBe(false);
    });
  });

  describe('message streaming', () => {
    it('should handle start event', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get WebSocket instance
      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
      });

      expect(result.current.isStreaming).toBe(true);
      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0].role).toBe('assistant');
      expect(result.current.messages[0].content).toBe('');
    });

    it('should accumulate chunk events', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({ type: 'chunk', content: 'Hello' });
        instance.simulateMessage({ type: 'chunk', content: ' ' });
        instance.simulateMessage({ type: 'chunk', content: 'World' });
      });

      // Advance timers to trigger flush (30ms interval)
      await act(async () => {
        vi.advanceTimersByTime(30);
      });

      expect(result.current.messages[0].content).toBe('Hello World');
    });

    it('should handle action events immediately (not buffered)', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({
          type: 'action',
          tool: 'file_write',
          args: { file_path: '/test.txt' },
          step: 1,
        });
      });

      // Action events should appear immediately without needing to wait for flush interval
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].type).toBe('action');
      expect(result.current.streamEvents[0].tool).toBe('file_write');
    });

    it('should handle observation events immediately (not buffered)', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({
          type: 'observation',
          content: 'File written successfully',
          success: true,
          step: 1,
        });
      });

      // Observation events should appear immediately without needing to wait for flush interval
      // This ensures file_edit and other tool results appear in real-time
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].type).toBe('observation');
      expect(result.current.streamEvents[0].success).toBe(true);
    });

    it('should handle end event', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({ type: 'chunk', content: 'Final message' });
        instance.simulateMessage({ type: 'end' });
      });

      await act(async () => {
        vi.advanceTimersByTime(30);
      });

      expect(result.current.isStreaming).toBe(false);
      expect(result.current.streamEvents).toEqual([]);
    });

    it('should handle action_args_chunk events immediately (not buffered)', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({
          type: 'action_args_chunk',
          tool: 'file_edit',
          partial_args: '{"file_path": "/test.txt", "content": "partial...',
          step: 1,
        });
      });

      // action_args_chunk should appear immediately without needing to wait for flush interval
      // This enables real-time "📝 writing on paper" progress display
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].type).toBe('action_args_chunk');
      expect(result.current.streamEvents[0].tool).toBe('file_edit');
      expect(result.current.streamEvents[0].partial_args).toBe('{"file_path": "/test.txt", "content": "partial...');
    });

    it('should remove action_args_chunk when action event arrives (both are immediate)', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({
          type: 'action_args_chunk',
          tool: 'file_write',
          partial_args: '{"file_path": "/test.txt"',
          step: 1,
        });
      });

      // action_args_chunk appears immediately (no 30ms delay)
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].type).toBe('action_args_chunk');

      act(() => {
        instance.simulateMessage({
          type: 'action',
          tool: 'file_write',
          args: { file_path: '/test.txt', content: 'Hello World' },
          step: 1,
        });
      });

      // Action events are immediate and filter out action_args_chunk for the same tool
      // action_args_chunk should be removed, only action should remain
      const argChunks = result.current.streamEvents.filter(
        (e) => e.type === 'action_args_chunk'
      );
      expect(argChunks).toHaveLength(0);

      const actionEvents = result.current.streamEvents.filter(
        (e) => e.type === 'action'
      );
      expect(actionEvents).toHaveLength(1);
      expect(actionEvents[0].tool).toBe('file_write');
    });
  });

  describe('sendMessage', () => {
    it('should send message via WebSocket', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        result.current.sendMessage('Hello, world!');
      });

      expect(instance.sentMessages).toHaveLength(1);
      const sentData = JSON.parse(instance.sentMessages[0]);
      expect(sentData.type).toBe('message');
      expect(sentData.content).toBe('Hello, world!');
    });

    it('should add user message to local state', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      act(() => {
        result.current.sendMessage('Test message');
      });

      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0].role).toBe('user');
      expect(result.current.messages[0].content).toBe('Test message');
    });

    it('should not send empty messages', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        result.current.sendMessage('   ');
      });

      expect(instance.sentMessages).toHaveLength(0);
      expect(result.current.messages).toHaveLength(0);
    });
  });

  describe('cancelStream', () => {
    it('should send cancel message', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        result.current.cancelStream();
      });

      const cancelMessage = instance.sentMessages.find((msg: string) => {
        const data = JSON.parse(msg);
        return data.type === 'cancel';
      });

      expect(cancelMessage).toBeDefined();
    });

    it('should handle cancelled event', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({ type: 'chunk', content: 'Partial content' });
      });

      await act(async () => {
        vi.advanceTimersByTime(30);
      });

      act(() => {
        instance.simulateMessage({ type: 'cancelled' });
      });

      expect(result.current.isStreaming).toBe(false);
    });
  });

  describe('error handling', () => {
    it('should handle error events', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({ type: 'error', content: 'Connection failed' });
      });

      expect(result.current.error).toBe('Connection failed');
      expect(result.current.isStreaming).toBe(false);
    });

    it('should clear error', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'error', content: 'Test error' });
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });

    it('should handle WebSocket connection errors', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateError(new Error('WebSocket error'));
      });

      expect(result.current.error).toBe('Connection error occurred');
      expect(result.current.isStreaming).toBe(false);
    });
  });

  describe('cleanup', () => {
    it('should close WebSocket on unmount', async () => {
      const { unmount } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      unmount();

      expect(instance.readyState).toBe(MockWebSocket.CLOSED);
    });
  });

  describe('title updates', () => {
    it('should invalidate queries on title_updated event', async () => {
      const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'title_updated', title: 'New Title' });
      });

      expect(invalidateQueriesSpy).toHaveBeenCalled();
    });
  });

  describe('Bug Fix: Message persistence during navigation', () => {
    it('BF2-001: messages should be properly initialized from initialMessages on first mount', async () => {
      const initialMessages = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'Existing message 1',
          created_at: '2024-01-01T00:00:00Z',
        },
        {
          id: 'msg-2',
          role: 'assistant' as const,
          content: 'Existing message 2',
          created_at: '2024-01-01T00:00:10Z',
        },
      ];

      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session', initialMessages }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toEqual(initialMessages);
      expect(result.current.messages).toHaveLength(2);
    });

    it('BF2-002: messages should NOT be overwritten when initialMessages changes to empty array', async () => {
      const initialMessages = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'Important message',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const { result, rerender } = renderHook(
        ({ sessionId, initialMessages }) => useOptimizedStreaming({ sessionId, initialMessages }),
        {
          wrapper: getWrapper(),
          initialProps: { sessionId: 'test-session', initialMessages },
        }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toEqual(initialMessages);

      // Simulate navigation causing initialMessages to become empty
      rerender({ sessionId: 'test-session', initialMessages: [] });

      await act(async () => {
        vi.runAllTimers();
      });

      // Messages should NOT be overwritten - they should persist
      expect(result.current.messages).toEqual(initialMessages);
      expect(result.current.messages).toHaveLength(1);
    });

    it('BF2-003: messages should be updated when initialMessages has MORE messages than current state', async () => {
      const initialMessages = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'Message 1',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const { result, rerender } = renderHook(
        ({ sessionId, initialMessages }) => useOptimizedStreaming({ sessionId, initialMessages }),
        {
          wrapper: getWrapper(),
          initialProps: { sessionId: 'test-session', initialMessages },
        }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toHaveLength(1);

      // Simulate new messages being added
      const updatedMessages = [
        ...initialMessages,
        {
          id: 'msg-2',
          role: 'assistant' as const,
          content: 'Message 2',
          created_at: '2024-01-01T00:00:10Z',
        },
      ];

      rerender({ sessionId: 'test-session', initialMessages: updatedMessages });

      await act(async () => {
        vi.runAllTimers();
      });

      // Messages should be updated with new data
      expect(result.current.messages).toEqual(updatedMessages);
      expect(result.current.messages).toHaveLength(2);
    });

    it('BF2-004: messages should persist during active streaming when component remounts', async () => {
      const initialMessages = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'User message',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const { result, unmount, rerender } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session', initialMessages }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      // Get the first WebSocket instance
      const instance = wsInstances[0];

      // Start streaming
      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({ type: 'chunk', content: 'Streaming...' });
      });

      await act(async () => {
        vi.advanceTimersByTime(30);
      });

      expect(result.current.isStreaming).toBe(true);
      expect(result.current.messages).toHaveLength(2); // User message + streaming message

      // Simulate component remounting (navigation away and back during streaming)
      // The initialMessages might be empty temporarily
      rerender();

      await act(async () => {
        vi.runAllTimers();
      });

      // Messages should NOT disappear
      expect(result.current.messages).toHaveLength(2);
    });

    it('BF2-005: hasInitializedRef should prevent re-initialization after first mount', async () => {
      const initialMessages = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'First message',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const { result, rerender } = renderHook(
        ({ sessionId, initialMessages }) => useOptimizedStreaming({ sessionId, initialMessages }),
        {
          wrapper: getWrapper(),
          initialProps: { sessionId: 'test-session', initialMessages },
        }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toEqual(initialMessages);

      // Send a new message via WebSocket
      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        result.current.sendMessage('Second message');
      });

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toHaveLength(2);

      // Trigger re-render with same initialMessages
      rerender({ sessionId: 'test-session', initialMessages });

      await act(async () => {
        vi.runAllTimers();
      });

      // Should NOT reset to initialMessages - should keep both messages
      expect(result.current.messages).toHaveLength(2);
    });

    it('BF2-006: messages persist when navigating back to chat during streaming', async () => {
      const existingMessages = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'Existing message before streaming',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const { result, rerender } = renderHook(
        ({ sessionId, initialMessages }) => useOptimizedStreaming({ sessionId, initialMessages }),
        {
          wrapper: getWrapper(),
          initialProps: { sessionId: 'test-session', initialMessages: existingMessages },
        }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toHaveLength(1);

      // Start streaming
      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        result.current.sendMessage('Trigger streaming');
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({ type: 'chunk', content: 'Streaming content...' });
      });

      await act(async () => {
        vi.advanceTimersByTime(30);
      });

      expect(result.current.messages).toHaveLength(3); // existing + user + assistant streaming

      // Simulate navigation away (initialMessages becomes empty)
      rerender({ sessionId: 'test-session', initialMessages: [] });

      await act(async () => {
        vi.runAllTimers();
      });

      // Messages should NOT disappear
      expect(result.current.messages).toHaveLength(3);
      expect(result.current.messages[0].content).toBe('Existing message before streaming');
    });

    it('BF2-007: state initialization starts with empty array, then populates from initialMessages', async () => {
      const initialMessages = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'Test message',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session', initialMessages }),
        { wrapper: getWrapper() }
      );

      // Before running timers, messages should be populated from initialMessages
      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toEqual(initialMessages);
    });

    it('BF2-008: should only update when initialMessages has more messages than current state', async () => {
      const oneMessage = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'Message 1',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const { result, rerender } = renderHook(
        ({ sessionId, initialMessages }) => useOptimizedStreaming({ sessionId, initialMessages }),
        {
          wrapper: getWrapper(),
          initialProps: { sessionId: 'test-session', initialMessages: oneMessage },
        }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toHaveLength(1);

      // Add a local message
      // Get the first WebSocket instance
      const instance = wsInstances[0];

      act(() => {
        result.current.sendMessage('Local message');
      });

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toHaveLength(2);

      // Try to update with same initialMessages (only 1 message)
      rerender({ sessionId: 'test-session', initialMessages: oneMessage });

      await act(async () => {
        vi.runAllTimers();
      });

      // Should NOT overwrite - should keep 2 messages
      expect(result.current.messages).toHaveLength(2);
    });

    it('BF2-009: empty initialMessages on first mount results in empty messages', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session', initialMessages: [] }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toEqual([]);
    });

    it('BF2-010: messages are preserved across multiple navigation cycles', async () => {
      const initialMessages = [
        {
          id: 'msg-1',
          role: 'user' as const,
          content: 'Persistent message',
          created_at: '2024-01-01T00:00:00Z',
        },
      ];

      const { result, rerender } = renderHook(
        ({ sessionId, initialMessages }) => useOptimizedStreaming({ sessionId, initialMessages }),
        {
          wrapper: getWrapper(),
          initialProps: { sessionId: 'test-session', initialMessages },
        }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      expect(result.current.messages).toHaveLength(1);

      // First navigation - empty initialMessages
      rerender({ sessionId: 'test-session', initialMessages: [] });
      await act(async () => {
        vi.runAllTimers();
      });
      expect(result.current.messages).toHaveLength(1);

      // Second navigation - empty initialMessages
      rerender({ sessionId: 'test-session', initialMessages: [] });
      await act(async () => {
        vi.runAllTimers();
      });
      expect(result.current.messages).toHaveLength(1);

      // Third navigation - back with initialMessages
      rerender({ sessionId: 'test-session', initialMessages });
      await act(async () => {
        vi.runAllTimers();
      });
      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0].content).toBe('Persistent message');
    });
  });

  describe('Bug Fix 2: Immediate observation and action streaming', () => {
    it('BF2-001: observation events should appear immediately without buffering delay', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({
          type: 'observation',
          content: 'File edit completed',
          success: true,
          metadata: { file: 'test.txt' },
          step: 1,
        });
      });

      // Should appear immediately - NO 30ms delay
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].type).toBe('observation');
      expect(result.current.streamEvents[0].content).toBe('File edit completed');
      expect(result.current.streamEvents[0].success).toBe(true);
    });

    it('BF2-002: action events should appear immediately without buffering delay', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({
          type: 'action',
          tool: 'file_edit',
          args: { file_path: '/test.txt', content: 'new content' },
          step: 1,
        });
      });

      // Should appear immediately - NO 30ms delay
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].type).toBe('action');
      expect(result.current.streamEvents[0].tool).toBe('file_edit');
    });

    it('BF2-003: multiple observation events appear in real-time during streaming', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({
          type: 'observation',
          content: 'First observation',
          success: true,
          step: 1,
        });
      });

      // First observation appears immediately
      expect(result.current.streamEvents).toHaveLength(1);

      act(() => {
        instance.simulateMessage({
          type: 'observation',
          content: 'Second observation',
          success: true,
          step: 2,
        });
      });

      // Second observation also appears immediately
      expect(result.current.streamEvents).toHaveLength(2);
      expect(result.current.streamEvents[0].content).toBe('First observation');
      expect(result.current.streamEvents[1].content).toBe('Second observation');
    });

    it('BF2-004: action and observation events appear immediately even when interleaved with chunks', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({ type: 'chunk', content: 'Some text...' });
        instance.simulateMessage({
          type: 'action',
          tool: 'bash',
          args: { command: 'ls' },
          step: 1,
        });
        instance.simulateMessage({ type: 'chunk', content: 'More text...' });
        instance.simulateMessage({
          type: 'observation',
          content: 'Command output',
          success: true,
          step: 1,
        });
      });

      // Action and observation should appear immediately, even though chunks are buffered
      const actionEvents = result.current.streamEvents.filter(e => e.type === 'action');
      const observationEvents = result.current.streamEvents.filter(e => e.type === 'observation');

      expect(actionEvents).toHaveLength(1);
      expect(observationEvents).toHaveLength(1);
      expect(actionEvents[0].tool).toBe('bash');
      expect(observationEvents[0].content).toBe('Command output');
    });

    it('BF2-005: file_edit observations are displayed in real-time', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        // Simulate file_edit tool usage
        instance.simulateMessage({
          type: 'action',
          tool: 'file_edit',
          args: { file_path: '/src/app.tsx' },
          step: 1,
        });
      });

      // Action appears immediately
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].tool).toBe('file_edit');

      act(() => {
        // File edit result
        instance.simulateMessage({
          type: 'observation',
          content: 'File successfully edited',
          success: true,
          metadata: { lines_changed: 5 },
          step: 1,
        });
      });

      // Observation appears immediately (no buffering)
      expect(result.current.streamEvents).toHaveLength(2);
      expect(result.current.streamEvents[1].type).toBe('observation');
      expect(result.current.streamEvents[1].content).toBe('File successfully edited');
      expect(result.current.streamEvents[1].success).toBe(true);
    });

    it('BF2-006: observation events do not go through eventBufferRef', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({
          type: 'observation',
          content: 'Immediate observation',
          success: true,
          step: 1,
        });
      });

      // Observation should appear immediately, even without advancing timers
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].content).toBe('Immediate observation');

      // Advancing timers should not change anything
      await act(async () => {
        vi.advanceTimersByTime(30);
      });

      // Still only 1 event (not duplicated)
      expect(result.current.streamEvents).toHaveLength(1);
    });

    it('BF2-007: action and action_args_chunk events do not go through eventBufferRef', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({
          type: 'action',
          tool: 'bash',
          args: { command: 'pwd' },
          step: 1,
        });
      });

      // Action should appear immediately, even without advancing timers
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].tool).toBe('bash');

      // Advancing timers should not change anything
      await act(async () => {
        vi.advanceTimersByTime(30);
      });

      // Still only 1 event (not duplicated)
      expect(result.current.streamEvents).toHaveLength(1);

      // Now test action_args_chunk immediate display
      act(() => {
        instance.simulateMessage({
          type: 'action_args_chunk',
          tool: 'file_edit',
          partial_args: '{"file_path": "test.ts"',
          step: 2,
        });
      });

      // action_args_chunk should also appear immediately without advancing timers
      expect(result.current.streamEvents).toHaveLength(2);
      expect(result.current.streamEvents[1].type).toBe('action_args_chunk');
      expect(result.current.streamEvents[1].tool).toBe('file_edit');

      // Advancing timers should not duplicate the event
      await act(async () => {
        vi.advanceTimersByTime(30);
      });

      // Still only 2 events (not duplicated)
      expect(result.current.streamEvents).toHaveLength(2);
    });

    it('BF2-008: multiple action_args_chunk events stream in real-time for file_edit progress', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        // Simulate real-time streaming of arguments as LLM generates them
        instance.simulateMessage({
          type: 'action_args_chunk',
          tool: 'file_edit',
          partial_args: '{"file_path"',
          step: 1,
        });
      });

      // First chunk appears immediately
      expect(result.current.streamEvents).toHaveLength(1);
      expect(result.current.streamEvents[0].partial_args).toBe('{"file_path"');

      act(() => {
        instance.simulateMessage({
          type: 'action_args_chunk',
          tool: 'file_edit',
          partial_args: '{"file_path": "/src',
          step: 1,
        });
      });

      // Second chunk appears immediately
      expect(result.current.streamEvents).toHaveLength(2);
      expect(result.current.streamEvents[1].partial_args).toBe('{"file_path": "/src');

      act(() => {
        instance.simulateMessage({
          type: 'action_args_chunk',
          tool: 'file_edit',
          partial_args: '{"file_path": "/src/app.tsx", "content": "import React',
          step: 1,
        });
      });

      // Third chunk appears immediately (real-time "📝 writing on paper" effect)
      expect(result.current.streamEvents).toHaveLength(3);
      expect(result.current.streamEvents[2].partial_args).toContain('import React');
    });

    it('BF2-009: chunk events are still buffered while action/observation/action_args_chunk are immediate', async () => {
      const { result } = renderHook(
        () => useOptimizedStreaming({ sessionId: 'test-session' }),
        { wrapper: getWrapper() }
      );

      await act(async () => {
        vi.runAllTimers();
      });

      const instance = wsInstances[0];

      act(() => {
        instance.simulateMessage({ type: 'start' });
        instance.simulateMessage({ type: 'chunk', content: 'Buffered ' });
        instance.simulateMessage({
          type: 'action_args_chunk',
          tool: 'file_write',
          partial_args: '{"content": "test"}',
          step: 1,
        });
        instance.simulateMessage({
          type: 'action',
          tool: 'grep',
          args: { pattern: 'test' },
          step: 2,
        });
        instance.simulateMessage({ type: 'chunk', content: 'chunk' });
      });

      // action_args_chunk and action appear immediately (not buffered)
      const argsChunks = result.current.streamEvents.filter(e => e.type === 'action_args_chunk');
      expect(argsChunks).toHaveLength(1);
      expect(argsChunks[0].tool).toBe('file_write');

      const actionEvents = result.current.streamEvents.filter(e => e.type === 'action');
      expect(actionEvents).toHaveLength(1);
      expect(actionEvents[0].tool).toBe('grep');

      // But message content is not yet flushed
      expect(result.current.messages[0].content).toBe('');

      // Advance timers to flush chunks
      await act(async () => {
        vi.advanceTimersByTime(30);
      });

      // Now chunks are flushed to message content
      expect(result.current.messages[0].content).toBe('Buffered chunk');

      // Action and action_args_chunk events still there
      const finalActionEvents = result.current.streamEvents.filter(e => e.type === 'action');
      expect(finalActionEvents).toHaveLength(1);

      const finalArgsChunks = result.current.streamEvents.filter(e => e.type === 'action_args_chunk');
      expect(finalArgsChunks).toHaveLength(1);
    });
  });
});
