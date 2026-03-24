import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GroupCard } from '../GroupCard';

const TOOLS = [
  { name: 'read', description: 'Read file', params: {} },
  { name: 'write', description: 'Write file', params: {} },
];

describe('GroupCard', () => {
  it('renders group name and tool count', () => {
    render(<GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={false} onOpen={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText('Filesystem')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('calls onOpen when main area is clicked', () => {
    const onOpen = vi.fn();
    render(<GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={false} onOpen={onOpen} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText('Filesystem'));
    expect(onOpen).toHaveBeenCalledWith('Filesystem');
  });

  it('expands to show tool names when expand button clicked', () => {
    render(<GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={false} onOpen={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTitle('Show tools'));
    expect(screen.getByText('read')).toBeInTheDocument();
    expect(screen.getByText('write')).toBeInTheDocument();
  });

  it('shows close button when active', () => {
    render(<GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={true} onOpen={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByTitle('Remove group')).toBeInTheDocument();
  });
});
