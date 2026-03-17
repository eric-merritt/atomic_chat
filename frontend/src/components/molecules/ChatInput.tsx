import { useState, useRef, useEffect } from 'react';
import { Input } from '../atoms/Input';
import { Button } from '../atoms/Button';

interface ChatInputProps {
  onSend: (text: string) => void;
  onCancel: () => void;
  onClear: () => void;
  streaming: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, onCancel, onClear, streaming, disabled }: ChatInputProps) {
  const [text, setText] = useState('');
  const [showTooltip, setShowTooltip] = useState(false);
  const tooltipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => { if (tooltipTimer.current) clearTimeout(tooltipTimer.current); };
  }, []);

  const handleSend = () => {
    if (text.trim()) {
      onSend(text.trim());
      setText('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !streaming) {
      if (disabled) {
        setShowTooltip(true);
        if (tooltipTimer.current) clearTimeout(tooltipTimer.current);
        tooltipTimer.current = setTimeout(() => setShowTooltip(false), 2000);
      } else {
        handleSend();
      }
    }
  };

  return (
    <>
      <div className="relative flex-[3] min-w-0">
        <Input
          className="w-full"
          placeholder={disabled ? "Select a model to chat..." : "Type a message..."}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        {showTooltip && (
          <div className="absolute -top-9 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-lg text-xs whitespace-nowrap bg-[var(--glass-bg-solid)] border border-[var(--accent)] text-[var(--text)] shadow-lg animate-[msgIn_0.15s_ease-out]">
            Please select a model
          </div>
        )}
      </div>
      <Button variant="ghost" onClick={onClear}>Clear</Button>
      {streaming ? (
        <Button variant="danger" onClick={onCancel}>Stop</Button>
      ) : (
        <Button variant="primary" onClick={handleSend} disabled={disabled || !text.trim()}>Send</Button>
      )}
    </>
  );
}
