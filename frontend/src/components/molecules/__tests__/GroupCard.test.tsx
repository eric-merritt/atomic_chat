import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GroupCard } from '../GroupCard';

const TOOLS = [
  { name: 'read', description: 'Read file', params: {} },
  { name: 'write', description: 'Write file', params: {} },
];

describe('GroupCard', () => {
  it('renders group name and tool count', () => {
    render(<GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={false} onToggle={vi.fn()} />);
    expect(screen.getByText('Filesystem')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('calls onToggle when the card is clicked', () => {
    const onToggle = vi.fn();
    render(<GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={false} onToggle={onToggle} />);
    fireEvent.click(screen.getByText('Filesystem'));
    expect(onToggle).toHaveBeenCalledWith('Filesystem');
  });

  it('calls onToggle when an active card is clicked (toggle off)', () => {
    const onToggle = vi.fn();
    render(<GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={true} onToggle={onToggle} />);
    fireEvent.click(screen.getByText('Filesystem'));
    expect(onToggle).toHaveBeenCalledWith('Filesystem');
  });

  it('expand button does not trigger onToggle', () => {
    const onToggle = vi.fn();
    render(<GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={false} onToggle={onToggle} />);
    fireEvent.click(screen.getByTitle('Show tools'));
    expect(onToggle).not.toHaveBeenCalled();
    expect(screen.getByText('read')).toBeInTheDocument();
    expect(screen.getByText('write')).toBeInTheDocument();
  });
});
