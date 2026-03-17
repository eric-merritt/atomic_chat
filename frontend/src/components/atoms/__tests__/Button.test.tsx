import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '../Button';

describe('Button', () => {
  it('renders with label', () => {
    render(<Button variant="primary" onClick={() => {}}>Send</Button>);
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });

  it('calls onClick', async () => {
    const fn = vi.fn();
    render(<Button variant="primary" onClick={fn}>Click</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(fn).toHaveBeenCalledOnce();
  });

  it('is disabled when disabled prop is true', () => {
    render(<Button variant="primary" onClick={() => {}} disabled>Send</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('applies variant classes', () => {
    const { container } = render(<Button variant="danger" onClick={() => {}}>Del</Button>);
    expect(container.firstChild).toHaveClass('bg-[var(--danger)]');
  });
});
