import { useRef, useCallback } from 'react';
import { parseStreamLine, type StreamEvent } from '../atoms/stream';
import { streamChatAsync } from '../api/chat';

export function parseNdjsonLines(text: string): {
  events: StreamEvent[];
  remainder: string;
} {
  const lines = text.split('\n');
  const remainder = lines.pop() ?? '';
  const events: StreamEvent[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const raw = JSON.parse(trimmed);
      const ev = parseStreamLine(raw);
      if (ev) events.push(ev);
    } catch {
      // skip malformed lines
    }
  }

  return { events, remainder };
}

export interface StreamCallbacks {
  onEvent: (event: StreamEvent) => void;
  onDone: () => void;
  onError: (error: string) => void;
}

export function useStream() {
  const abortRef = useRef<(() => void) | null>(null);

  const start = useCallback(async (message: string, callbacks: StreamCallbacks) => {
    // Abort any existing stream before starting a new one
    abortRef.current?.();

    try {
      const { reader, abort } = await streamChatAsync(message);
      abortRef.current = abort;

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseNdjsonLines(buffer);
        buffer = remainder;

        for (const ev of events) {
          callbacks.onEvent(ev);
        }
      }

      if (buffer.trim()) {
        const { events } = parseNdjsonLines(buffer + '\n');
        for (const ev of events) {
          callbacks.onEvent(ev);
        }
      }

      callbacks.onDone();
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        callbacks.onError(String(e));
      }
    } finally {
      abortRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.();
  }, []);

  return { start, stop };
}
