import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolExplorer } from '../ToolExplorer';
import { WorkspaceContext } from '../../../providers/WorkspaceProvider';
import type { LayoutState } from '../../../providers/WorkspaceProvider';

const GROUPS = [
  { name: 'Filesystem', tooltip: 'File ops', tools: [{ name: 'read', description: 'Read', params: {} }] },
  { name: 'Web Tools', tooltip: 'Web ops', tools: [{ name: 'web_search', description: 'Search', params: {} }] },
];

function renderWithContext(activeGroups: string[] = []) {
  const ctx = {
    layout: 'default' as LayoutState,
    setLayout: vi.fn(),
    groups: GROUPS,
    activeGroups,
    toggleGroup: vi.fn(),
    selectedTool: null,
    selectTool: vi.fn(),
    galleryPayload: null,
    showGallery: vi.fn(),
    clearGallery: vi.fn(),
  };
  return { ...render(
    <WorkspaceContext.Provider value={ctx}>
      <ToolExplorer />
    </WorkspaceContext.Provider>
  ), ctx };
}

describe('ToolExplorer', () => {
  it('renders all group cards', () => {
    renderWithContext();
    expect(screen.getByText('Filesystem')).toBeInTheDocument();
    expect(screen.getByText('Web Tools')).toBeInTheDocument();
  });

  it('filters groups by search', () => {
    renderWithContext();
    fireEvent.change(screen.getByPlaceholderText('Search tools...'), { target: { value: 'web' } });
    expect(screen.queryByText('Filesystem')).not.toBeInTheDocument();
    expect(screen.getByText('Web Tools')).toBeInTheDocument();
  });

  it('shows empty state when no matches', () => {
    renderWithContext();
    fireEvent.change(screen.getByPlaceholderText('Search tools...'), { target: { value: 'zzzzz' } });
    expect(screen.getByText('No matching tools')).toBeInTheDocument();
  });
});
