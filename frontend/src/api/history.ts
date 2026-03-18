import type { Message } from '../atoms/message';
import { createMessageFromHistory } from '../atoms/message';
import type { ApiResponse } from '../atoms/api';

export async function fetchHistory(): Promise<ApiResponse<Message[]>> {
  try {
    const resp = await fetch('/api/history', { credentials: 'include' });
    if (!resp.ok) {
      return { data: [], error: `Failed: ${resp.status}` };
    }
    const json = await resp.json();
    const messages = (json.history as Array<{ role: string; content: string }>)
      .map(createMessageFromHistory);
    return { data: messages };
  } catch (e) {
    return { data: [], error: String(e) };
  }
}

export async function clearHistory(): Promise<void> {
  await fetch('/api/history', { method: 'DELETE', credentials: 'include' });
}
