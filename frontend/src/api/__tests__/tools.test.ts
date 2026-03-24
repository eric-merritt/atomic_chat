import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchTools, toggleTool, toggleCategory } from '../tools';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => { mockFetch.mockReset(); });

const apiResponse = {
  available: [
    { index: 1, name: 'write', description: 'Write a file', params: {} },
  ],
  selected: [
    { index: 0, name: 'read', description: 'Read a file', params: {} },
  ],
};

describe('fetchTools', () => {
  it('transforms backend response into ToolCategory atoms', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => apiResponse });

    const result = await fetchTools();
    expect(result.data).toHaveLength(1);
    expect(result.data![0].name).toBe('Filesystem');
    expect(result.data![0].tools).toHaveLength(2);
    expect(result.data![0].tools[0].category).toBe('Filesystem');
    expect(result.data![0].someSelected).toBe(true);
    expect(result.data![0].allSelected).toBe(false);
    expect(result.data![0].selectedCount).toBe(1);
  });
});

describe('toggleTool', () => {
  it('posts tool index to select endpoint', async () => {
    // First call: fetchTools to populate index map
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => apiResponse });
    await fetchTools();

    // toggleTool: first fetches current state, then posts select/deselect
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => apiResponse })   // check state
      .mockResolvedValueOnce({ ok: true, json: async () => apiResponse });  // select call

    await toggleTool('write');
    // Third call should be the select POST (write is in available, not selected)
    expect(mockFetch).toHaveBeenCalledWith('/api/tools/select', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ index: 1 }),
    }));
  });
});

describe('toggleCategory', () => {
  it('posts to select/deselect for each tool in category', async () => {
    // First call: fetchTools to populate index map
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => apiResponse });
    await fetchTools();

    // toggleCategory: fetches current state, then selects/deselects each tool
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => apiResponse })   // check state
      .mockResolvedValueOnce({ ok: true, json: async () => apiResponse });  // select call

    await toggleCategory('Filesystem');
    // Should have called /api/tools to check state
    expect(mockFetch).toHaveBeenCalledWith('/api/tools', expect.objectContaining({ credentials: 'include' }));
  });
});
