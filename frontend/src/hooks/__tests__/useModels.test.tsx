import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ModelProvider } from '../../providers/ModelProvider';
import { useModels } from '../useModels';
import type { ReactNode } from 'react';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

const wrapper = ({ children }: { children: ReactNode }) => (
  <ModelProvider>{children}</ModelProvider>
);

const modelsResponse = {
  models: ['huihui_ai/qwen2.5-coder-abliterate:14b', 'llama3.1:8b'],
  current: 'huihui_ai/qwen2.5-coder-abliterate:14b',
};

beforeEach(() => { mockFetch.mockReset(); });

describe('useModels', () => {
  it('fetches models on mount', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => modelsResponse });
    const { result } = renderHook(() => useModels(), { wrapper });
    await waitFor(() => { expect(result.current.models).toHaveLength(2); });
    expect(result.current.current?.name).toBe('qwen2.5-coder-abliterate');
  });

  it('selects a model', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => modelsResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ model: 'llama3.1:8b' }) });
    const { result } = renderHook(() => useModels(), { wrapper });
    await waitFor(() => { expect(result.current.models).toHaveLength(2); });
    await act(async () => { await result.current.selectModel(result.current.models[1]); });
    expect(result.current.current?.name).toBe('llama3.1');
  });

  it('starts with loading true', () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => modelsResponse });
    const { result } = renderHook(() => useModels(), { wrapper });
    expect(result.current.loading).toBe(true);
  });
});
