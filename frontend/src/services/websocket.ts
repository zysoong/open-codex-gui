export interface ChatMessage {
  type: 'message' | 'chunk' | 'start' | 'end' | 'error' | 'user_message_saved' | 'thought' | 'action' | 'observation';
  content?: string;
  message_id?: string;
  tool?: string;
  args?: any;
  success?: boolean;
  step?: number;
}

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private onMessageCallback?: (message: ChatMessage) => void;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
  }

  connect(onMessage: (message: ChatMessage) => void): void {
    this.onMessageCallback = onMessage;

    const wsUrl = `ws://127.0.0.1:8000/api/v1/chats/${this.sessionId}/stream`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const message: ChatMessage = JSON.parse(event.data);
        if (this.onMessageCallback) {
          this.onMessageCallback(message);
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('WebSocket closed');
      this.attemptReconnect();
    };
  }

  sendMessage(content: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = {
        type: 'message',
        content,
      };
      this.ws.send(JSON.stringify(message));
    } else {
      console.error('WebSocket is not connected');
    }
  }

  close(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts && this.onMessageCallback) {
      this.reconnectAttempts++;
      console.log(`Reconnecting... (attempt ${this.reconnectAttempts})`);
      setTimeout(() => {
        this.connect(this.onMessageCallback!);
      }, 2000 * this.reconnectAttempts);
    }
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}
