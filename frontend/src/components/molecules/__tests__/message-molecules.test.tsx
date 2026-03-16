import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageBubble } from '../MessageBubble';
import { ImageThumbnail } from '../ImageThumbnail';
import { ThinkingIndicator } from '../ThinkingIndicator';
import type { Message } from '../../../atoms/message';

const userMsg: Message = {
  id: '1', role: 'user', content: 'Hello', images: [], toolCalls: [], timestamp: 1,
};

const assistantMsg: Message = {
  id: '2', role: 'assistant', content: 'Hi there', images: [], toolCalls: [], timestamp: 2,
};

describe('MessageBubble', () => {
  it('renders user message right-aligned', () => {
    const { container } = render(<MessageBubble message={userMsg} />);
    expect(container.firstChild).toHaveClass('self-end');
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders assistant message left-aligned', () => {
    const { container } = render(<MessageBubble message={assistantMsg} />);
    expect(container.firstChild).toHaveClass('self-start');
  });
});

describe('ImageThumbnail', () => {
  it('renders image with caption', () => {
    render(<ImageThumbnail src="/img.jpg" filename="img.jpg" sizeKb={42} onClick={() => {}} />);
    expect(screen.getByRole('img')).toHaveAttribute('src', '/img.jpg');
    expect(screen.getByText(/img\.jpg/)).toBeInTheDocument();
  });
});

describe('ThinkingIndicator', () => {
  it('renders with working label', () => {
    render(<ThinkingIndicator label="Working..." elapsed={3} preview="" />);
    expect(screen.getByText('Working...')).toBeInTheDocument();
    expect(screen.getByText('3s')).toBeInTheDocument();
  });
});
