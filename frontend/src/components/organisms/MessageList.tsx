import { useRef, useEffect, useState } from 'react';
import { MessageBubble } from '../molecules/MessageBubble';
import { ImageThumbnail } from '../molecules/ImageThumbnail';
import { ThinkingIndicator } from '../molecules/ThinkingIndicator';
import { useChat } from '../../hooks/useChat';

interface MessageListProps {
  onImageClick: (src: string, caption: string) => void;
}

export function MessageList({ onImageClick }: MessageListProps) {
  const { messages, streaming } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [elapsed, setElapsed] = useState(0);

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

  return (
    <div className="overflow-y-auto px-6 py-5 flex flex-col gap-2">
      <div className="mt-auto" />
      {messages.map((msg) => (
        <div key={msg.id}>
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
        </div>
      ))}
      {streaming && (
        <ThinkingIndicator label="Working..." elapsed={elapsed} preview="" />
      )}
      <div ref={bottomRef} />
    </div>
  );
}
