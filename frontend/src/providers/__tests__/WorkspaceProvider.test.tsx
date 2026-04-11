import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { WorkspaceProvider } from '../WorkspaceProvider';
import { useWorkspace } from '../../hooks/useWorkspace';
import type { ReactNode } from 'react';

vi.mock('../../api/workflowGroups', () => ({
  fetchWorkflowGroups: vi.fn().mockResolvedValue({
    groups: [
      { name: 'Filesystem', tooltip: 'File ops', tools: [{ name: 'read', description: 'Read file', params: {} }] },
      { name: 'Web Tools', tooltip: 'Web ops', tools: [{ name: 'web_search', description: 'Search', params: {} }] },
    ],
  }),
  selectGroup: vi.fn().mockResolvedValue({ ok: true, selected: [] }),
}));

vi.mock('../../hooks/useTools', () => ({
  useTools: () => ({ categories: [], selected: [], toggleTool: vi.fn(), toggleCategory: vi.fn(), refreshTools: vi.fn() }),
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <WorkspaceProvider>{children}</WorkspaceProvider>
);

describe('WorkspaceProvider', () => {
  it('starts in default layout', () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });
    expect(result.current.layout).toBe('default');
    expect(result.current.activeGroups).toEqual([]);
  });

  it('opens a group and transitions to workspace layout', async () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });
    await act(async () => {
      await result.current.openGroup('Filesystem');
    });
    expect(result.current.layout).toBe('workspace-chat');
    expect(result.current.activeGroups).toContain('Filesystem');
  });

  it('closes all groups and reverts to default', async () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });
    await act(async () => {
      await result.current.openGroup('Filesystem');
    });
    await act(async () => {
      await result.current.closeGroup('Filesystem');
    });
    expect(result.current.layout).toBe('default');
    expect(result.current.activeGroups).toEqual([]);
  });
});
