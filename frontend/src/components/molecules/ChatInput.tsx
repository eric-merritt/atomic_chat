import { useState, useRef, useEffect, useCallback } from 'react';
import { Input } from '../atoms/Input';
import { Button } from '../atoms/Button';

const HISTORY_KEY = 'atomic-chat-input-history';
const MAX_HISTORY = 10;

function loadHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory(history: string[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, MAX_HISTORY)));
}

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
  const historyRef = useRef(loadHistory());
  const historyIndex = useRef(-1);
  const savedDraft = useRef('');

  useEffect(() => {
    return () => { if (tooltipTimer.current) clearTimeout(tooltipTimer.current); };
  }, []);

  const handleSend = useCallback(() => {
    if (text.trim()) {
      const msg = text.trim();
      // Add to history (dedupe: remove if already exists, then prepend)
      historyRef.current = [msg, ...historyRef.current.filter((m) => m !== msg)].slice(0, MAX_HISTORY);
      saveHistory(historyRef.current);
      historyIndex.current = -1;
      savedDraft.current = '';
      onSend(msg);
      setText('');
    }
  }, [text, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowUp' && historyRef.current.length > 0) {
      e.preventDefault();
      if (historyIndex.current === -1) savedDraft.current = text;
      const next = Math.min(historyIndex.current + 1, historyRef.current.length - 1);
      historyIndex.current = next;
      setText(historyRef.current[next]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex.current <= 0) {
        historyIndex.current = -1;
        setText(savedDraft.current);
      } else {
        historyIndex.current -= 1;
        setText(historyRef.current[historyIndex.current]);
      }
    } else if (e.key === 'Enter' && !streaming) {
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
          onChange={(e) => { setText(e.target.value); historyIndex.current = -1; }}
          onKeyDown={handleKeyDown}
        />
        {showTooltip && (
          <div className="absolute -top-12 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-lg text-xs whitespace-nowrap bg-[var(--glass-bg-solid)] border border-[var(--accent)] text-[var(--text)] shadow-lg animate-[msgIn_0.15s_ease-out]">
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
