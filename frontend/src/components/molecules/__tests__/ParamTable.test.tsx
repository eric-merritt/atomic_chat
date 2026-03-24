import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ParamTable } from '../ParamTable';

const PARAMS = {
  path: { type: 'string', required: true, description: 'File path' },
  lines: { type: 'integer', required: false, description: 'Number of lines' },
  recursive: { type: 'boolean', required: false, description: 'Recurse into dirs' },
};

describe('ParamTable', () => {
  it('renders param names and types in read-only mode', () => {
    render(<ParamTable params={PARAMS} interactive={false} values={{}} onChange={vi.fn()} />);
    expect(screen.getByText('path')).toBeInTheDocument();
    expect(screen.getByText('string')).toBeInTheDocument();
    expect(screen.getByText('integer')).toBeInTheDocument();
  });

  it('renders inputs in interactive mode', () => {
    render(<ParamTable params={PARAMS} interactive={true} values={{}} onChange={vi.fn()} />);
    const inputs = screen.getAllByRole('textbox');
    expect(inputs.length).toBeGreaterThan(0);
  });

  it('calls onChange when interactive value changes', () => {
    const onChange = vi.fn();
    render(<ParamTable params={PARAMS} interactive={true} values={{}} onChange={onChange} />);
    const input = screen.getAllByRole('textbox')[0];
    fireEvent.change(input, { target: { value: '/tmp/test' } });
    expect(onChange).toHaveBeenCalledWith('path', '/tmp/test');
  });
});
