import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatInput } from '../ChatInput';
import { ToolChip } from '../ToolChip';

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

