import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { ParticleCanvas } from '../ParticleCanvas';

beforeEach(() => {
  // Mock canvas context
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    closePath: vi.fn(),
    fillStyle: '',
  })) as any;
});

describe('ParticleCanvas', () => {
  it('renders a canvas element', () => {
    const { container } = render(<ParticleCanvas theme="obsidian" />);
    expect(container.querySelector('canvas')).toBeInTheDocument();
  });

  it('applies fixed positioning to fill viewport', () => {
    const { container } = render(<ParticleCanvas theme="obsidian" />);
    const canvas = container.querySelector('canvas')!;
    expect(canvas.className).toContain('fixed');
    expect(canvas.className).toContain('inset-0');
  });
});
