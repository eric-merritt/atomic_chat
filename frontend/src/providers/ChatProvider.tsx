import { createContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react';
import type { Message } from '../atoms/message';
import { createMessage } from '../atoms/message';
import { cancelChat, respondToRecommendation } from '../api/chat';
import { clearHistory as apiClearHistory } from '../api/history';
import { getConversation } from '../api/conversations';
import { useStream } from '../hooks/useStream';
import { useModels } from '../hooks/useModels';
import type { ToolActivity } from '../components/atoms/ToolCallPanel';

interface Recommendation {
  groups: string[];
  reason: string;
}

interface ChatContextValue {
  messages: Message[];
  sendMessage: (text: string) => void;
  cancelStream: () => void;
  clearHistory: () => Promise<void>;
  streaming: boolean;
  ready: boolean;
  conversationId: string | null;
  loadConversation: (id: string) => Promise<void>;
  newConversation: () => void;
  toolActivities: ToolActivity[];
  recommendation: Recommendation | null;
  acceptRecommendation: () => void;
  dismissRecommendation: () => void;
}

export const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [toolActivities, setToolActivities] = useState<ToolActivity[]>([]);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const streamingRef = useRef(false);
  const lastEventRef = useRef(0);
  const watchdogRef = useRef<ReturnType<typeof setInterval> | null>(null);
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
      setConversationId(null);
    }
    prevModelRef.current = currentModel;
  }, [currentModel, stop]);

  const loadConversation = useCallback(async (id: string) => {
    const data = await getConversation(id, 1, 50);
    if (data.messages) {
      const loaded: Message[] = data.messages.map((m: { id: string; role: string; content: string; images?: { src: string; filename: string; sizeKb: number }[]; tool_calls?: { tool: string; input: string }[]; created_at: string }) =>
        ({
          id: m.id,
          role: m.role as 'user' | 'assistant' | 'error',
          content: m.content,
          images: m.images || [],
          toolCalls: m.tool_calls || [],
          timestamp: new Date(m.created_at).getTime(),
        })
      );
      setMessages(loaded);
      setConversationId(id);
    }
  }, []);

  const newConversation = useCallback(() => {
    setMessages([]);
    setConversationId(null);
  }, []);

  const sendMessage = useCallback((text: string) => {
    if (streamingRef.current || !currentModel) return;
    const userMsg = createMessage('user', text);
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);
    setToolActivities([]);
    streamingRef.current = true;

    let assistantCreated = false;
    lastEventRef.current = Date.now();

    // Watchdog: if no stream events arrive for 90s, auto-reset
    if (watchdogRef.current) clearInterval(watchdogRef.current);
    watchdogRef.current = setInterval(() => {
      if (streamingRef.current && Date.now() - lastEventRef.current > 90_000) {
        console.warn('[ChatProvider] Stream stale for 90s, auto-resetting');
        stop();
        cancelChat();
        setStreaming(false);
        streamingRef.current = false;
        if (watchdogRef.current) { clearInterval(watchdogRef.current); watchdogRef.current = null; }
      }
    }, 10_000);

    start(text, {
      onEvent: (ev) => {
        lastEventRef.current = Date.now();
        switch (ev.type) {
          case 'meta':
            if (ev.conversationId) setConversationId(ev.conversationId);
            break;
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
          case 'tool_call':
            setToolActivities((prev) => [...prev, {
              type: 'call', tool: ev.tool, content: ev.input, timestamp: Date.now(),
            }]);
            break;
          case 'tool_result':
            setToolActivities((prev) => [...prev, {
              type: 'result', tool: ev.tool, content: ev.output, timestamp: Date.now(),
            }]);
            break;
          case 'recommendation':
            setRecommendation({ groups: ev.groups, reason: ev.reason });
            break;
          case 'error':
            setMessages((prev) => [...prev, createMessage('error', ev.message)]);
            break;
        }
      },
      onDone: () => {
        setStreaming(false);
        streamingRef.current = false;
        if (watchdogRef.current) { clearInterval(watchdogRef.current); watchdogRef.current = null; }
      },
      onError: (error) => {
        setMessages((prev) => [...prev, createMessage('error', error)]);
        setStreaming(false);
        streamingRef.current = false;
        if (watchdogRef.current) { clearInterval(watchdogRef.current); watchdogRef.current = null; }
      },
    }, conversationId);
  }, [start, currentModel, conversationId]);

  const cancelStream = useCallback(() => {
    stop();
    cancelChat();
    setStreaming(false);
    streamingRef.current = false;
  }, [stop]);

  const clearHistory = useCallback(async () => {
    await apiClearHistory();
    setMessages([]);
    setConversationId(null);
  }, []);

  const acceptRecommendation = useCallback(async () => {
    if (!recommendation || !conversationId) return;
    await respondToRecommendation(conversationId, recommendation.groups);
    setRecommendation(null);
  }, [recommendation, conversationId]);

  const dismissRecommendation = useCallback(async () => {
    if (!conversationId) return;
    await respondToRecommendation(conversationId, []);
    setRecommendation(null);
  }, [conversationId]);

  return (
    <ChatContext.Provider value={{
      messages, sendMessage, cancelStream, clearHistory, streaming,
      ready: !!currentModel, conversationId, loadConversation, newConversation,
      toolActivities, recommendation, acceptRecommendation, dismissRecommendation,
    }}>
      {children}
    </ChatContext.Provider>
  );
}
