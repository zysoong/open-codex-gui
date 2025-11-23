import { memo, useState, useCallback, KeyboardEvent } from 'react';

interface MessageInputProps {
  onSend: (message: string) => void;
  onCancel: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export const MessageInput = memo(({ onSend, onCancel, isStreaming, disabled = false }: MessageInputProps) => {
  const [input, setInput] = useState('');

  const handleSend = useCallback(() => {
    if (input.trim() && !isStreaming) {
      onSend(input);
      setInput('');
    }
  }, [input, isStreaming, onSend]);

  const handleKeyPress = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleCancel = useCallback(() => {
    onCancel();
  }, [onCancel]);

  return (
    <div className="chat-input-container">
      <div className="chat-input-wrapper">
        <textarea
          className="chat-input"
          placeholder="Type your message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          rows={1}
          disabled={disabled || isStreaming}
        />
        <button
          className={`send-btn ${isStreaming ? 'stop-btn' : ''}`}
          onClick={isStreaming ? handleCancel : handleSend}
          disabled={isStreaming ? false : !input.trim()}
          title={isStreaming ? 'Stop generating' : 'Send message'}
        >
          {isStreaming ? (
            'Stop'
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path
                d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
});

MessageInput.displayName = 'MessageInput';
