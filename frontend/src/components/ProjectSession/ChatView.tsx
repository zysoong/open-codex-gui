import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { messagesAPI } from '@/services/api';
import { useChatStore } from '@/stores/chatStore';
import { ChatWebSocket, ChatMessage } from '@/services/websocket';
import type { ChatSession } from '@/types';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import SandboxControls from './SandboxControls';
import './ChatView.css';

interface ChatViewProps {
  session: ChatSession;
}

export default function ChatView({ session }: ChatViewProps) {
  const queryClient = useQueryClient();
  const wsRef = useRef<ChatWebSocket | null>(null);
  const {
    streamingMessage,
    isStreaming,
    agentActions,
    error,
    appendStreamingMessage,
    setStreaming,
    clearStreamingMessage,
    addAgentAction,
    clearAgentActions,
    setError,
    clearError,
  } = useChatStore();

  // Fetch messages
  const { data: messagesData } = useQuery({
    queryKey: ['messages', session.id],
    queryFn: () => messagesAPI.list(session.id),
  });

  // Setup WebSocket
  useEffect(() => {
    const ws = new ChatWebSocket(session.id);

    ws.connect((message: ChatMessage) => {
      switch (message.type) {
        case 'start':
          setStreaming(true);
          clearStreamingMessage();
          clearAgentActions();
          break;

        case 'chunk':
          if (message.content) {
            appendStreamingMessage(message.content);
          }
          break;

        case 'thought':
          if (message.content) {
            appendStreamingMessage(message.content);
            addAgentAction({
              type: 'thought',
              content: message.content,
              step: message.step,
            });
          }
          break;

        case 'action':
          addAgentAction({
            type: 'action',
            content: `Using tool: ${message.tool}`,
            tool: message.tool,
            args: message.args,
            step: message.step,
          });
          break;

        case 'observation':
          addAgentAction({
            type: 'observation',
            content: message.content || '',
            success: message.success,
            step: message.step,
          });
          break;

        case 'end':
          setStreaming(false);
          // Refresh messages to include the new assistant message
          queryClient.invalidateQueries({ queryKey: ['messages', session.id] });
          clearStreamingMessage();
          break;

        case 'error':
          console.error('WebSocket error:', message.content);
          setError(message.content || 'An unknown error occurred');
          setStreaming(false);
          clearStreamingMessage();
          break;

        case 'user_message_saved':
          // Refresh messages to include the new user message
          queryClient.invalidateQueries({ queryKey: ['messages', session.id] });
          break;
      }
    });

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [session.id]);

  const handleSendMessage = (content: string) => {
    // Clear any previous errors when sending a new message
    clearError();

    if (wsRef.current && wsRef.current.isConnected()) {
      wsRef.current.sendMessage(content);
    } else {
      console.error('WebSocket is not connected');
      setError('WebSocket is not connected. Please refresh the page.');
    }
  };

  const messages = messagesData?.messages || [];

  return (
    <div className="chat-view">
      <div className="chat-header">
        <h2>{session.name}</h2>
      </div>

      <SandboxControls sessionId={session.id} />

      <MessageList
        messages={messages}
        streamingMessage={streamingMessage}
        isStreaming={isStreaming}
        agentActions={agentActions}
      />

      {error && (
        <div className="chat-error-banner">
          <div className="error-content">
            <span className="error-icon">⚠️</span>
            <div className="error-message">{error}</div>
            <button
              className="error-close-btn"
              onClick={clearError}
              aria-label="Close error"
            >
              ×
            </button>
          </div>
        </div>
      )}

      <MessageInput
        onSend={handleSendMessage}
        disabled={isStreaming}
      />
    </div>
  );
}
