import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatInput } from '../ChatInput';
import { ToolChip } from '../ToolChip';
import { ToolCategory } from '../ToolCategory';
import { ToolRow } from '../ToolRow';

describe('ChatInput', () => {
  it('calls onSend when send button clicked', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} onCancel={() => {}} onClear={() => {}} streaming={false} />);
    const input = screen.getByPlaceholderText('Type a message...');
    await userEvent.type(input, 'hello');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(onSend).toHaveBeenCalledWith('hello');
  });

  it('shows stop button when streaming', () => {
    render(<ChatInput onSend={() => {}} onCancel={() => {}} onClear={() => {}} streaming={true} />);
    expect(screen.getByRole('button', { name: 'Stop' })).toBeVisible();
  });
});

describe('ToolChip', () => {
  it('shows count', () => {
    render(<ToolChip selected={['a', 'b']} onRemove={() => {}} />);
    expect(screen.getByText('2 tools')).toBeInTheDocument();
  });

  it('hides when no tools selected', () => {
    const { container } = render(<ToolChip selected={[]} onRemove={() => {}} />);
    expect(container.firstChild).toBeNull();
  });
});

describe('ToolCategory', () => {
  it('renders category name and count', () => {
    render(
      <ToolCategory
        name="Filesystem"
        count={10}
        selectedCount={5}
        allSelected={false}
        someSelected={true}
        expanded={false}
        onToggleExpand={() => {}}
        onToggleAll={() => {}}
      />
    );
    expect(screen.getByText('Filesystem')).toBeInTheDocument();
    expect(screen.getByText('5/10')).toBeInTheDocument();
  });
});

describe('ToolRow', () => {
  it('renders tool name and description', () => {
    render(<ToolRow name="read_file" description="Read a file" selected={true} onToggle={() => {}} />);
    expect(screen.getByText('read_file')).toBeInTheDocument();
    expect(screen.getByText('Read a file')).toBeInTheDocument();
  });
});
