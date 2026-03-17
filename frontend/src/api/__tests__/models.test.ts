import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchModels, selectModel } from '../models';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => { mockFetch.mockReset(); });

describe('fetchModels', () => {
  it('parses model strings into Model atoms', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        models: ['huihui_ai/qwen2.5-coder-abliterate:14b', 'llama3.1:8b'],
        current: 'huihui_ai/qwen2.5-coder-abliterate:14b',
      }),
    });

    const result = await fetchModels();
    expect(result.data).toHaveLength(2);
    expect(result.data![0].devTeam).toBe('huihui_ai');
    expect(result.data![0].name).toBe('qwen2.5-coder-abliterate');
    expect(result.data![0].numParams).toBe('14b');
    expect(result.data![1].devTeam).toBeNull();
    expect(result.data![1].name).toBe('llama3.1');
  });

  it('returns error on fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });

    const result = await fetchModels();
    expect(result.error).toBeTruthy();
    expect(result.data).toEqual([]);
  });
});

describe('selectModel', () => {
  it('posts model id to API', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ model: 'llama3.1:8b' }),
    });

    await selectModel({
      devTeam: null, name: 'llama3.1', numParams: '8b', available: true,
      format: null, maker: null, year: null, description: null,
      goodAt: null, notSoGoodAt: null, idealUseCases: null, contextWindow: null,
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/models', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ model: 'llama3.1:8b' }),
    }));
  });
});
