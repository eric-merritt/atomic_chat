import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchWorkflowGroups, selectGroup, clearWorkflowGroupsCache } from '../workflowGroups';

const MOCK_GROUPS = {
  groups: [
    {
      name: 'Filesystem',
      tooltip: 'File operations',
      tools: [
        { name: 'read', description: 'Read a file', params: { path: { type: 'string', required: true, description: 'File path' } } },
      ],
    },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
  clearWorkflowGroupsCache();
});

describe('fetchWorkflowGroups', () => {
  it('fetches and returns groups', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_GROUPS,
    } as Response);

    const result = await fetchWorkflowGroups();
    expect(result.groups).toHaveLength(1);
    expect(result.groups[0].name).toBe('Filesystem');
    expect(fetch).toHaveBeenCalledWith('/api/workflows', expect.objectContaining({ credentials: 'include' }));
  });
});

describe('selectGroup', () => {
  it('posts group activation', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ok: true, selected: ['read'] }),
    } as Response);

    const result = await selectGroup('Filesystem', true);
    expect(result.ok).toBe(true);
    expect(fetch).toHaveBeenCalledWith('/api/tools/select-group', expect.objectContaining({ method: 'POST' }));
  });
});
