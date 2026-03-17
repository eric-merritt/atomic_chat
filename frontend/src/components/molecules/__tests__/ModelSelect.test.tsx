import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ModelSelect } from '../ModelSelect';
import { ModelProvider } from '../../../providers/ModelProvider';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => { mockFetch.mockReset(); });

const modelsResp = {
  models: ['huihui_ai/qwen2.5-coder-abliterate:14b', 'llama3.1:8b'],
  current: 'llama3.1:8b',
};

describe('ModelSelect', () => {
  it('renders model options after loading', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => modelsResp });
    render(<ModelProvider><ModelSelect /></ModelProvider>);
    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });
    expect(screen.getAllByRole('option').length).toBeGreaterThanOrEqual(2);
  });
});
