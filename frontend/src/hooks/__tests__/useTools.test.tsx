import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ToolProvider } from '../../providers/ToolProvider';
import { useTools } from '../useTools';
import type { ReactNode } from 'react';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

const wrapper = ({ children }: { children: ReactNode }) => (
  <ToolProvider>{children}</ToolProvider>
);

const toolsResponse = {
  available: [
    { index: 1, name: 'fetch_url', description: 'Fetch', params: {} },
  ],
  selected: [
    { index: 0, name: 'web_search', description: 'Search', params: {} },
  ],
};

beforeEach(() => { mockFetch.mockReset(); });

describe('useTools', () => {
  it('fetches categories on mount', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => toolsResponse });
    const { result } = renderHook(() => useTools(), { wrapper });
    await waitFor(() => { expect(result.current.categories).toHaveLength(1); });
    expect(result.current.selected).toEqual(['web_search']);
  });

  it('toggles a tool', async () => {
    const toggledResponse = {
      available: [],
      selected: [
        { index: 0, name: 'web_search', description: 'Search', params: {} },
        { index: 1, name: 'fetch_url', description: 'Fetch', params: {} },
      ],
    };
    mockFetch.mockResolvedValue({ ok: true, json: async () => toolsResponse });
    const { result } = renderHook(() => useTools(), { wrapper });
    await waitFor(() => { expect(result.current.categories).toHaveLength(1); });

    mockFetch.mockResolvedValue({ ok: true, json: async () => toggledResponse });
    await act(async () => { await result.current.toggleTool('fetch_url'); });
    expect(result.current.selected).toEqual(['web_search', 'fetch_url']);
  });
});
