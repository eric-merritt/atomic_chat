import { useRef, useEffect } from 'react';
import { useChat } from '../../hooks/useChat';

interface ChatPopoverProps {
  open: boolean;
  onClose: () => void;
}

export function ChatPopover({ open, onClose }: ChatPopoverProps) {
  const { messages } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [open, messages]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={popoverRef}
      className="fixed bottom-16 right-4 w-80 h-96 rounded-xl border border-[var(--accent)] bg-[var(--glass-bg-solid)] backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.3)] flex flex-col z-50 animate-[msgIn_0.15s_ease-out]"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--glass-border)]">
        <span className="text-xs font-semibold text-[var(--accent)]">Chat</span>
        <button
          className="text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer text-sm"
          onClick={onClose}
        >
          &times;
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-2">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`text-[10px] font-mono p-2 rounded-lg max-w-[90%] ${
              m.role === 'user'
                ? 'self-end bg-[var(--msg-user)] text-[var(--text)]'
                : 'self-start bg-[var(--msg-assistant)] text-[var(--text)]'
            }`}
          >
            {m.content.slice(0, 500) + (m.content.length > 500 ? '\u2026' : '')}
          </div>
        ))}
      </div>
    </div>
  );
}
