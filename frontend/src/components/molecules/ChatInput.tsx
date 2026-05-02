import { useState, useRef, useEffect, useCallback } from 'react';
import { Input } from '../atoms/Input';
import { Button } from '../atoms/Button';
import { EmojiPicker } from './EmojiPicker';

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

interface DroppedImage {
  path: string;
  preview: string;
  filename: string;
}

interface ChatInputProps {
  onSend: (text: string) => void;
  onCancel: () => void;
  onClear: () => void;
  streaming: boolean;
  disabled?: boolean;
  droppedImage?: DroppedImage | null;
  onClearImage?: () => void;
}

export function ChatInput({ onSend, onCancel, onClear, streaming, disabled, droppedImage, onClearImage }: ChatInputProps) {
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
    const hasImage = !!droppedImage;
    const hasText = !!text.trim();
    if (!hasText && !hasImage) return;

    let msg = text.trim();
    if (droppedImage) {
      const imageTag = `[Image: ${droppedImage.path}]`;
      msg = msg ? `${imageTag}\n${msg}` : `${imageTag}\nDescribe this image.`;
      onClearImage?.();
    }

    historyRef.current = [msg, ...historyRef.current.filter((m) => m !== msg)].slice(0, MAX_HISTORY);
    saveHistory(historyRef.current);
    historyIndex.current = -1;
    savedDraft.current = '';
    onSend(msg);
    setText('');
  }, [text, onSend, droppedImage, onClearImage]);

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
    } else if (e.key === 'Enter') {
      if (disabled) {
        setShowTooltip(true);
        if (tooltipTimer.current) clearTimeout(tooltipTimer.current);
        tooltipTimer.current = setTimeout(() => setShowTooltip(false), 2000);
      } else {
        handleSend();
      }
    }
  };

  const insertEmoji = (emoji: string) => {
    setText(text + emoji);
  };

  const canSend = !disabled && (!!text.trim() || !!droppedImage);

  return (
    <>
      <div className="relative flex-[3] min-w-0">
        {droppedImage && (
          <div className="absolute -top-14 left-0 flex items-center gap-2 px-2 py-1 rounded-lg bg-[var(--glass-bg-solid)] border border-[var(--accent)] shadow-md">
            <img src={droppedImage.preview} alt={droppedImage.filename} className="w-8 h-8 rounded object-cover" />
            <span className="text-xs text-[var(--text-muted)] max-w-[12rem] truncate">{droppedImage.filename}</span>
            <button
              onClick={onClearImage}
              className="text-[var(--text-muted)] hover:text-[var(--text)] leading-none text-sm ml-1 cursor-pointer"
              aria-label="Remove image"
            >✕</button>
          </div>
        )}
        <Input
          className="w-full"
          placeholder={disabled ? "Select a model to chat..." : droppedImage ? "Ask about the image..." : "Type a message..."}
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
      <EmojiPicker onEmojiSelect={insertEmoji} />
      <Button variant="ghost" onClick={onClear}>Clear</Button>
      {streaming && <Button variant="danger" onClick={onCancel}>Stop</Button>}
      <Button variant="primary" onClick={handleSend} disabled={!canSend}>Send</Button>
    </>
  );
}
