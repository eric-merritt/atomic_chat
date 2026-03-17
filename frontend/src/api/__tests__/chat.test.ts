import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cancelChat } from '../chat';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => { mockFetch.mockReset(); });

describe('cancelChat', () => {
  it('posts to cancel endpoint', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    await cancelChat();
    expect(mockFetch).toHaveBeenCalledWith('/api/chat/cancel', { method: 'POST' });
  });
});
