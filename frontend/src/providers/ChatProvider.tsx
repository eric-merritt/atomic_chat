import { createContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react';
import type { Message, ToolCallPair } from '../atoms/message';
import { createMessage } from '../atoms/message';
import { cancelChat, summarizeContext as apiSummarize } from '../api/chat';
import { clearHistory as apiClearHistory } from '../api/history';
import { getConversation } from '../api/conversations';
import { useStream } from '../hooks/useStream';
import { useModels } from '../hooks/useModels';

export interface TaskReview {
  id: string;
  title: string;
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
  contextPct: number;
  summarizing: boolean;
  summarizeContext: () => void;
  tasksUnderReview: TaskReview[];
  clearTasksUnderReview: () => void;
}

interface LoadedRow {
  id: string;
  role: string;
  content: string;
  images?: { src: string; filename: string; sizeKb: number }[];
  tool_calls?: { name?: string; tool?: string; id?: string; input?: string }[];
  created_at: string;
}

function toolRowToPair(row: LoadedRow): ToolCallPair {
  const meta = row.tool_calls?.[0] || {};
  let result: unknown = row.content;
  try { result = JSON.parse(row.content); } catch { /* keep raw string */ }
  return {
    tool: meta.tool || meta.name || 'tool',
    params: {},
    result,
    status: 'done',
    contentOffset: 0,
  };
}

function blankAssistant(pairs: ToolCallPair[], timestamp: number): Message {
  return { ...createMessage('assistant', ''), toolPairs: pairs, timestamp };
}

// Persisted conversations store each tool result as its own role="tool" row,
// emitted BEFORE the assistant text that the tool calls belong to. The live
// renderer expects tool calls inside an assistant message's toolPairs, so on
// load we fold consecutive tool rows into the next assistant message (or a
// blank assistant bubble if the turn ended on tool rows).
function buildLoadedMessages(rows: LoadedRow[]): Message[] {
  const out: Message[] = [];
  let pendingPairs: ToolCallPair[] = [];

  for (const row of rows) {
    if (row.role === 'tool') {
      pendingPairs.push(toolRowToPair(row));
      continue;
    }
    const timestamp = new Date(row.created_at).getTime();
    if (row.role === 'assistant') {
      out.push({
        id: row.id,
        role: 'assistant',
        content: row.content,
        images: row.images || [],
        toolCalls: [],
        toolPairs: pendingPairs,
        timestamp,
      });
      pendingPairs = [];
      continue;
    }
    // user / error row: flush any orphaned tool pairs into their own bubble first
    if (pendingPairs.length) {
      out.push(blankAssistant(pendingPairs, timestamp));
      pendingPairs = [];
    }
    out.push({
      id: row.id,
      role: row.role as 'user' | 'error',
      content: row.content,
      images: row.images || [],
      toolCalls: [],
      toolPairs: [],
      timestamp,
    });
  }
  if (pendingPairs.length) {
    out.push(blankAssistant(pendingPairs, Date.now()));
  }
  return out;
}

export const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [contextPct, setContextPct] = useState(0);
  const [summarizing, setSummarizing] = useState(false);
  const [tasksUnderReview, setTasksUnderReview] = useState<TaskReview[]>([]);
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
      setMessages(buildLoadedMessages(data.messages));
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
              const pair = { tool: ev.tool, params, result: null, status: 'streaming' as const, contentOffset: last?.role === 'assistant' ? last.content.length : 0 }
              if (last?.role === 'assistant') {
                return [...msgs.slice(0, -1), { ...last, toolPairs: [...last.toolPairs, pair] }]
              }
              // Tool called before any token — create assistant message now
              if (!assistantCreated) assistantCreated = true
              return [...msgs, { ...createMessage('assistant', ''), toolPairs: [pair] }]
            })
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
            break
          }
          case 'task_review':
            setTasksUnderReview(ev.tasks);
            break;
          case 'context_pct':
            setContextPct(ev.pct);
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
        // Auto-summarize when context hits the 75% threshold
        setContextPct((pct) => {
          if (pct >= 75 && conversationId) {
            setSummarizing(true);
            apiSummarize(conversationId)
              .then((r) => setContextPct(r.context_pct))
              .catch((e: unknown) => {
                const msg = e instanceof Error ? e.message : String(e);
                console.error('[ChatProvider] Auto-summarize failed:', msg);
                setMessages((prev) => [...prev, createMessage('error',
                  'Context compression failed — conversation history was not compacted. ' +
                  'You may hit the context limit soon. Try summarizing manually or start a new conversation.'
                )]);
              })
              .finally(() => setSummarizing(false));
          }
          return pct;
        });
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
    setContextPct(0);
  }, []);

  const summarizeContext = useCallback(() => {
    if (!conversationId || summarizing || streaming) return;
    setSummarizing(true);
    apiSummarize(conversationId)
      .then((r) => {
        setContextPct(r.context_pct);
        return loadConversation(conversationId);
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e);
        console.error('[ChatProvider] Manual summarize failed:', msg);
        setMessages((prev) => [...prev, createMessage('error',
          `Failed to compress context — ${msg}. ` +
          'Your conversation history was not modified. Try again or start a new conversation.'
        )]);
      })
      .finally(() => setSummarizing(false));
  }, [conversationId, summarizing, streaming, loadConversation]);

  const clearTasksUnderReview = useCallback(() => setTasksUnderReview([]), []);

  return (
    <ChatContext.Provider value={{
      messages, sendMessage, cancelStream, clearHistory, streaming,
      ready: !!currentModel, conversationId, loadConversation, newConversation,
      contextPct, summarizing, summarizeContext,
      tasksUnderReview, clearTasksUnderReview,
    }}>
      {children}
    </ChatContext.Provider>
  );
}
