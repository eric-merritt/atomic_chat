import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolWorkspace } from '../ToolWorkspace';
import { WorkspaceContext } from '../../../providers/WorkspaceProvider';
import type { LayoutState } from '../../../providers/WorkspaceProvider';
import type { WorkflowGroup } from '../../../api/workflowGroups';

const GROUPS: WorkflowGroup[] = [
  {
    name: 'Filesystem',
    tooltip: 'File ops',
    tools: [
      { name: 'read', description: 'Read a file from disk', params: { path: { type: 'string', required: true, description: 'File path' } } },
      { name: 'write', description: 'Write to a file', params: { path: { type: 'string', required: true, description: 'File path' }, content: { type: 'string', required: true, description: 'Content' } } },
    ],
  },
];

function renderWithContext() {
  const ctx = {
    layout: 'workspace-chat' as LayoutState,
    setLayout: vi.fn(),
    groups: GROUPS,
    activeGroups: ['Filesystem'],
    openGroup: vi.fn(),
    closeGroup: vi.fn(),
    selectedTool: null,
    selectTool: vi.fn(),
  };
  return { ...render(
    <WorkspaceContext.Provider value={ctx}>
      <ToolWorkspace />
    </WorkspaceContext.Provider>
  ), ctx };
}

describe('ToolWorkspace', () => {
  it('renders active group sections', () => {
    renderWithContext();
    expect(screen.getByText('Filesystem')).toBeInTheDocument();
  });

  it('renders tool buttons for active groups', () => {
    renderWithContext();
    expect(screen.getByText('read')).toBeInTheDocument();
    expect(screen.getByText('write')).toBeInTheDocument();
  });

  it('shows tool detail when tool button is clicked', () => {
    const { ctx } = renderWithContext();
    fireEvent.click(screen.getByText('read'));
    expect(ctx.selectTool).toHaveBeenCalledWith('read');
  });
});
