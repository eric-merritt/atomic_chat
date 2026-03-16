import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ToolProvider } from '../../providers/ToolProvider';
import { useTools } from '../useTools';
import type { ReactNode } from 'react';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

const wrapper = ({ children }: { children: ReactNode }) => (
  <ToolProvider>{children}</ToolProvider>
);

const toolsResponse = {
  categories: [{
    name: 'Web',
    tools: [
      { name: 'web_search', description: 'Search', params: {}, selected: true },
      { name: 'fetch_url', description: 'Fetch', params: {}, selected: false },
    ],
  }],
  selected: ['web_search'],
};

beforeEach(() => { mockFetch.mockReset(); });

describe('useTools', () => {
  it('fetches categories on mount', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => toolsResponse });
    const { result } = renderHook(() => useTools(), { wrapper });
    await waitFor(() => { expect(result.current.categories).toHaveLength(1); });
    expect(result.current.selected).toEqual(['web_search']);
  });

  it('toggles a tool', async () => {
    const toggledResponse = {
      ...toolsResponse,
      categories: [{
        ...toolsResponse.categories[0],
        tools: toolsResponse.categories[0].tools.map((t) =>
          t.name === 'fetch_url' ? { ...t, selected: true } : t
        ),
      }],
      selected: ['web_search', 'fetch_url'],
    };
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => toolsResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => toggledResponse });
    const { result } = renderHook(() => useTools(), { wrapper });
    await waitFor(() => { expect(result.current.categories).toHaveLength(1); });
    await act(async () => { await result.current.toggleTool('fetch_url'); });
    expect(result.current.selected).toEqual(['web_search', 'fetch_url']);
  });
});
