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
          toolPairs: [],
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
    if (!currentModel) return;
    let actualText = text;
    if (streamingRef.current) {
      stop();
      cancelChat();
      setStreaming(false);
      streamingRef.current = false;
      if (watchdogRef.current) { clearInterval(watchdogRef.current); watchdogRef.current = null; }
      actualText = `[User interrupted previous response to add the following context/task:]\n${text}`;
    }
    const userMsg = createMessage('user', actualText);
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

    start(actualText, {
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
          case 'tool_call': {
            let params: unknown = ev.input
            try { params = JSON.parse(ev.input) } catch { /* keep raw string */ }

            setMessages(prev => {
              const msgs = [...prev]
              const last = msgs[msgs.length - 1]
              const pair = { tool: ev.tool, params, result: null, status: 'streaming' as const }
              if (last?.role === 'assistant') {
                return [...msgs.slice(0, -1), { ...last, toolPairs: [...last.toolPairs, pair] }]
              }
              // Tool called before any token — create assistant message now
              if (!assistantCreated) assistantCreated = true
              return [...msgs, { ...createMessage('assistant', ''), toolPairs: [pair] }]
            })
            // Keep existing toolActivities for backward compat
            setToolActivities(prev => [...prev, {
              type: 'call' as const, tool: ev.tool, content: ev.input, timestamp: Date.now(),
            }])
            break
          }
          case 'tool_result': {
            let result: unknown = ev.output
            try { result = JSON.parse(ev.output) } catch { /* keep raw string */ }

            setMessages(prev => {
              const msgs = [...prev]
              const last = msgs[msgs.length - 1]
              if (!last || last.role !== 'assistant') return prev
              const pairs = [...last.toolPairs]
              // Find the last streaming entry for this tool
              const idx = [...pairs.keys()]
                .filter(i => pairs[i].tool === ev.tool && pairs[i].status === 'streaming')
                .at(-1)
              if (idx === undefined) {
                console.warn('[ChatProvider] tool_result for', ev.tool, 'has no matching streaming pair')
                return prev
              }
              pairs[idx] = { ...pairs[idx], result, status: 'done' }
              return [...msgs.slice(0, -1), { ...last, toolPairs: pairs }]
            })
            setToolActivities(prev => [...prev, {
              type: 'result' as const, tool: ev.tool, content: ev.output, timestamp: Date.now(),
            }])
            break
          }
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
  }, [start, stop, currentModel, conversationId]);

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
