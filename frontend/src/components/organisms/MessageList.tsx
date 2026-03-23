import { useRef, useEffect, useState, useCallback } from 'react';
import { MessageBubble } from '../molecules/MessageBubble';
import { ImageThumbnail } from '../molecules/ImageThumbnail';
import { ThinkingIndicator } from '../molecules/ThinkingIndicator';
import { ToolCallPanel } from '../atoms/ToolCallPanel';
import { Timestamp } from '../atoms/Timestamp';
import { DateSeparator } from '../atoms/DateSeparator';
import { useChat } from '../../hooks/useChat';
import { NewConversationButton } from '../molecules/NewConversationButton';
import { ConversationTitle } from '../molecules/ConversationTitle';

interface MessageListProps {
  onImageClick: (src: string, caption: string) => void;
}

export function MessageList({ onImageClick }: MessageListProps) {
  const { messages, streaming, toolActivities } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const msgRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [elapsed, setElapsed] = useState(0);
  const [visibleDate, setVisibleDate] = useState(0);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  // Timer for thinking indicator
  useEffect(() => {
    if (!streaming) { setElapsed(0); return; }
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [streaming]);

  // Track which date is at the top of the scroll area
  const handleScroll = useCallback(() => {
    const container = scrollRef.current;
    if (!container || messages.length === 0) return;
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

  useEffect(() => {
    if (messages.length > 0 && !visibleDate) {
      setVisibleDate(messages[0].timestamp);
    }
  }, [messages, visibleDate]);

  return (
    <div ref={scrollRef} onScroll={handleScroll} className="relative overflow-y-auto px-6 pb-5 flex flex-col gap-2 backdrop-blur-sm border border-[var(--accent)] rounded-[14px] m-2">
      {visibleDate > 0 && (
        <DateSeparator timestamp={visibleDate} />
      )}
      <div className="flex items-center justify-between px-2 py-1">
        <ConversationTitle />
        <NewConversationButton />
      </div>
      <div className="mt-auto" />
      {(() => {
        // Find the last user message index so we can render ToolCallPanel right after it
        const lastUserIdx = toolActivities.length > 0
          ? messages.reduce((acc, m, i) => m.role === 'user' ? i : acc, -1)
          : -1;

        return messages.map((msg, idx) => {
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
              {idx === lastUserIdx && (
                <ToolCallPanel activities={toolActivities} />
              )}
            </div>
          );
        });
      })()}
      {streaming && (
        <ThinkingIndicator label="Working..." elapsed={elapsed} preview="" />
      )}
      <div ref={bottomRef} />
    </div>
  );
}
