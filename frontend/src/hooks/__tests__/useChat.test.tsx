import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ChatProvider } from '../../providers/ChatProvider';
import { ModelProvider } from '../../providers/ModelProvider';
import { useChat } from '../useChat';
import type { ReactNode } from 'react';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => { mockFetch.mockReset(); });

const wrapper = ({ children }: { children: ReactNode }) => (
  <ModelProvider>
    <ChatProvider>{children}</ChatProvider>
  </ModelProvider>
);

describe('useChat', () => {
  it('starts with empty messages and not streaming', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true, json: async () => ({ models: [], current: null }),
    });
    const { result } = renderHook(() => useChat(), { wrapper });
    await waitFor(() => {
      expect(result.current.messages).toEqual([]);
      expect(result.current.streaming).toBe(false);
    });
  });

  it('clearHistory empties messages and calls API', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ models: [], current: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ cleared: true }) });
    const { result } = renderHook(() => useChat(), { wrapper });
    await act(async () => { await result.current.clearHistory(); });
    expect(mockFetch).toHaveBeenCalledWith('/api/history', { method: 'DELETE' });
    expect(result.current.messages).toEqual([]);
  });
});
