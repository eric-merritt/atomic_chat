import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchHistory, clearHistory } from '../history';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => { mockFetch.mockReset(); });

describe('fetchHistory', () => {
  it('transforms history entries into Message atoms', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        history: [
          { role: 'user', content: 'hello' },
          { role: 'assistant', content: 'hi' },
        ],
      }),
    });
    const result = await fetchHistory();
    expect(result.data).toHaveLength(2);
    expect(result.data![0].role).toBe('user');
    expect(result.data![0].id).toBeTruthy();
    expect(result.data![0].images).toEqual([]);
    expect(result.data![0].toolCalls).toEqual([]);
    expect(result.data![0].timestamp).toBe(0);
  });
});

describe('clearHistory', () => {
  it('sends DELETE request', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ cleared: true }) });
    await clearHistory();
    expect(mockFetch).toHaveBeenCalledWith('/api/history', { method: 'DELETE' });
  });
});
