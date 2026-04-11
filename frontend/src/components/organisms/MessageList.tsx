import { useRef, useEffect, useState, useCallback } from 'react';
import { MessageBubble } from '../molecules/MessageBubble';
import { ImageThumbnail } from '../molecules/ImageThumbnail';
import { ThinkingIndicator } from '../molecules/ThinkingIndicator';
import { Timestamp } from '../atoms/Timestamp';
import { DateSeparator } from '../atoms/DateSeparator';
import { useChat } from '../../hooks/useChat';
import { NewConversationButton } from '../molecules/NewConversationButton';
import { ConversationTitle } from '../molecules/ConversationTitle';

interface MessageListProps {
  onImageClick: (src: string, caption: string) => void;
}

export function MessageList({ onImageClick }: MessageListProps) {
  const { messages, streaming } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const msgRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [elapsed, setElapsed] = useState(0);
  const [visibleDate, setVisibleDate] = useState(0);
  const [userScrolled, setUserScrolled] = useState(false);

  // Auto-scroll on new messages (only when user hasn't manually scrolled up)
  useEffect(() => {
    if (!userScrolled) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, streaming, userScrolled]);

  // Timer for thinking indicator
  useEffect(() => {
    if (!streaming) { setElapsed(0); return; }
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [streaming]);

  // Track scroll position: date header + userScrolled state
  const handleScroll = useCallback(() => {
    const container = scrollRef.current;
    if (!container) return;

    // Update userScrolled based on distance from bottom
    const atBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 40;
    setUserScrolled(!atBottom);

    // Track which date is at the top of the scroll area
    if (messages.length === 0) return;
    const top = container.getBoundingClientRect().top + 40;
    let ts = messages[0].timestamp;
    for (const msg of messages) {
      const el = msgRefs.current.get(msg.id);
      if (el && el.getBoundingClientRect().top <= top) {
        ts = msg.timestamp;
      }
    }
    setVisibleDate(ts);
  }, [messages]);

  const jumpToCurrent = useCallback(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    setUserScrolled(false);
  }, []);

  useEffect(() => {
    if (messages.length > 0 && !visibleDate) {
      setVisibleDate(messages[0].timestamp);
    }
  }, [messages, visibleDate]);

  return (
    <div className="relative m-2 flex flex-col overflow-hidden">
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 min-h-0 overflow-y-auto px-6 pb-5 flex flex-col gap-2 backdrop-blur-sm border border-[var(--accent)] rounded-[14px]">
        {visibleDate > 0 && (
          <DateSeparator timestamp={visibleDate} />
        )}
        <div className="flex items-center justify-between px-2 py-1">
          <ConversationTitle />
          <NewConversationButton />
        </div>
        <div className="mt-auto" />
        {messages.map((msg) => {
          const align = msg.role === 'user' ? 'right' : 'left';
          return (
            <div key={msg.id} ref={(el) => { if (el) msgRefs.current.set(msg.id, el); }} className="flex flex-col">
              <MessageBubble message={msg} />
              {msg.images.map((img, i) => (
                <ImageThumbnail
                  key={i}
                  src={img.src}
                  filename={img.filename}
                  sizeKb={img.sizeKb}
                  onClick={() => onImageClick(img.src, img.filename)}
                />
              ))}
              <Timestamp timestamp={msg.timestamp} align={align} />
            </div>
          );
        })}
        {streaming && (
          <ThinkingIndicator label="Working..." elapsed={elapsed} preview="" />
        )}
        <div ref={bottomRef} />
      </div>

      {userScrolled && (
        <button
          onClick={jumpToCurrent}
          className="absolute bottom-20 left-1/2 -translate-x-1/2 z-10 px-3 py-1.5 text-xs font-mono rounded-full transition-all duration-200 animate-[msgIn_0.2s_ease-out]"
          style={{
            background: 'color-mix(in srgb, var(--accent) 20%, transparent)',
            border: '1px solid color-mix(in srgb, var(--accent) 40%, transparent)',
            color: 'var(--accent)',
            boxShadow: '0 0 12px color-mix(in srgb, var(--accent) 30%, transparent)',
          }}
        >
          Jump to current ↓
        </button>
      )}
    </div>
  );
}
