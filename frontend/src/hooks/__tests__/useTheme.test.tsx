import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ThemeProvider } from '../../providers/ThemeProvider';
import { useTheme } from '../useTheme';
import type { ReactNode } from 'react';

const wrapper = ({ children }: { children: ReactNode }) => (
  <ThemeProvider>{children}</ThemeProvider>
);

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('useTheme', () => {
  it('defaults to obsidian', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme.id).toBe('obsidian');
  });

  it('sets data-theme attribute on html element', () => {
    renderHook(() => useTheme(), { wrapper });
    expect(document.documentElement.getAttribute('data-theme')).toBe('obsidian');
  });

  it('changes theme and persists to localStorage', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => { result.current.setTheme('carbon'); });
    expect(result.current.theme.id).toBe('carbon');
    expect(localStorage.getItem('agentic-theme')).toBe('carbon');
    expect(document.documentElement.getAttribute('data-theme')).toBe('carbon');
  });

  it('restores theme from localStorage', () => {
    localStorage.setItem('agentic-theme', 'frost');
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme.id).toBe('frost');
  });

  it('exposes all 6 themes', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.themes).toHaveLength(6);
  });
});
