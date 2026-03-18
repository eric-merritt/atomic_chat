import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Input } from '../Input';
import { Select } from '../Select';
import { Badge } from '../Badge';
import { Icon } from '../Icon';
import { Checkbox } from '../Checkbox';
import { StatusText } from '../StatusText';
import { Dot } from '../Dot';

describe('Input', () => {
  it('renders with placeholder', () => {
    render(<Input placeholder="Type..." onChange={() => {}} />);
    expect(screen.getByPlaceholderText('Type...')).toBeInTheDocument();
  });

  it('calls onChange', async () => {
    const fn = vi.fn();
    render(<Input onChange={fn} />);
    await userEvent.type(screen.getByRole('textbox'), 'hi');
    expect(fn).toHaveBeenCalled();
  });
});

describe('Select', () => {
  it('renders options', () => {
    render(
      <Select value="a" onChange={() => {}} options={[
        { value: 'a', label: 'Alpha' },
        { value: 'b', label: 'Beta' },
      ]} />
    );
    expect(screen.getAllByRole('option')).toHaveLength(2);
  });
});

describe('Badge', () => {
  it('renders count text', () => {
    render(<Badge>5 tools</Badge>);
    expect(screen.getByText('5 tools')).toBeInTheDocument();
  });
});

describe('Icon', () => {
  it('renders an SVG with correct size', () => {
    const { container } = render(<Icon name="wrench" size={24} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute('width', '24');
  });

  it('renders different icon names', () => {
    const { container } = render(<Icon name="atom" />);
    expect(container.querySelector('svg')).toBeInTheDocument();
  });
});

describe('Checkbox', () => {
  it('renders and responds to click', async () => {
    const fn = vi.fn();
    render(<Checkbox checked={false} onChange={fn} />);
    await userEvent.click(screen.getByRole('checkbox'));
    expect(fn).toHaveBeenCalled();
  });

  it('supports indeterminate state', () => {
    render(<Checkbox checked={false} indeterminate onChange={() => {}} />);
    const cb = screen.getByRole('checkbox') as HTMLInputElement;
    expect(cb.indeterminate).toBe(true);
  });
});

describe('StatusText', () => {
  it('renders text', () => {
    render(<StatusText>Loading...</StatusText>);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });
});

describe('Dot', () => {
  it('renders a span', () => {
    const { container } = render(<Dot />);
    expect(container.querySelector('span')).toBeInTheDocument();
  });
});
