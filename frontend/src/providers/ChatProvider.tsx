import { createContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react';
import type { Message } from '../atoms/message';
import { createMessage } from '../atoms/message';
import { cancelChat } from '../api/chat';
import { clearHistory as apiClearHistory } from '../api/history';
import { useStream } from '../hooks/useStream';
import { useModels } from '../hooks/useModels';

interface ChatContextValue {
  messages: Message[];
  sendMessage: (text: string) => void;
  cancelStream: () => void;
  clearHistory: () => Promise<void>;
  streaming: boolean;
}

export const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const streamingRef = useRef(false);
  const { start, stop } = useStream();
  const { current: currentModel } = useModels();
  const prevModelRef = useRef(currentModel);

  useEffect(() => {
    if (prevModelRef.current && currentModel && prevModelRef.current !== currentModel) {
      stop();
      cancelChat();
      setStreaming(false);
      streamingRef.current = false;
      setMessages([]);
    }
    prevModelRef.current = currentModel;
  }, [currentModel, stop]);

  const sendMessage = useCallback((text: string) => {
    if (streamingRef.current) return;
    const userMsg = createMessage('user', text);
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);
    streamingRef.current = true;

    let assistantCreated = false;

    start(text, {
      onEvent: (ev) => {
        switch (ev.type) {
          case 'token':
            setMessages((prev) => {
              if (!assistantCreated) {
                assistantCreated = true;
                return [...prev, createMessage('assistant', ev.token)];
              }
              const last = prev[prev.length - 1];
              return [
                ...prev.slice(0, -1),
                { ...last, content: last.content + ev.token },
              ];
            });
            break;
          case 'image':
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === 'assistant') {
                return [
                  ...prev.slice(0, -1),
                  { ...last, images: [...last.images, { src: ev.src, filename: ev.filename, sizeKb: ev.sizeKb }] },
                ];
              }
              return prev;
            });
            break;
          case 'error':
            setMessages((prev) => [...prev, createMessage('error', ev.message)]);
            break;
        }
      },
      onDone: () => { setStreaming(false); streamingRef.current = false; },
      onError: (error) => {
        setMessages((prev) => [...prev, createMessage('error', error)]);
        setStreaming(false);
        streamingRef.current = false;
      },
    });
  }, [start]);

  const cancelStream = useCallback(() => {
    stop();
    cancelChat();
    setStreaming(false);
    streamingRef.current = false;
  }, [stop]);

  const clearHistory = useCallback(async () => {
    await apiClearHistory();
    setMessages([]);
  }, []);

  return (
    <ChatContext.Provider value={{ messages, sendMessage, cancelStream, clearHistory, streaming }}>
      {children}
    </ChatContext.Provider>
  );
}
