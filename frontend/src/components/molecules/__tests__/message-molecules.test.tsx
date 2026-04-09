import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageBubble } from '../MessageBubble';
import { ImageThumbnail } from '../ImageThumbnail';
import { ThinkingIndicator } from '../ThinkingIndicator';
import type { Message } from '../../../atoms/message';

const userMsg: Message = {
  id: '1', role: 'user', content: 'Hello', images: [], toolCalls: [], toolPairs: [], timestamp: 1,
};

const assistantMsg: Message = {
  id: '2', role: 'assistant', content: 'Hi there', images: [], toolCalls: [], toolPairs: [], timestamp: 2,
};

describe('MessageBubble', () => {
  it('renders user message right-aligned', () => {
    render(<MessageBubble message={userMsg} />);
    expect(screen.getByText('Hello').closest('.self-end')).toBeInTheDocument();
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders assistant message left-aligned', () => {
    render(<MessageBubble message={assistantMsg} />);
    expect(screen.getByText('Hi there').closest('.self-start')).toBeInTheDocument();
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
