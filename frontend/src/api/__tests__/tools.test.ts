import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchTools, toggleTool, toggleCategory } from '../tools';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => { mockFetch.mockReset(); });

const apiResponse = {
  categories: [
    {
      name: 'Filesystem',
      tools: [
        { name: 'read_file', description: 'Read a file', params: {}, selected: true },
        { name: 'write_file', description: 'Write a file', params: {}, selected: false },
      ],
      all_selected: false,
      some_selected: true,
      count: 2,
      selected_count: 1,
    },
  ],
  selected: ['read_file'],
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
  it('posts tool name', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => apiResponse });
    await toggleTool('read_file');
    expect(mockFetch).toHaveBeenCalledWith('/api/tools/toggle', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ tool: 'read_file' }),
    }));
  });
});

describe('toggleCategory', () => {
  it('posts category name', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => apiResponse });
    await toggleCategory('Filesystem');
    expect(mockFetch).toHaveBeenCalledWith('/api/tools/toggle_category', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ category: 'Filesystem' }),
    }));
  });
});
