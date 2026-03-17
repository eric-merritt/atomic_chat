import { describe, it, expect } from 'vitest';
import { THEMES, getThemeById } from '../theme';

describe('THEMES', () => {
  it('has 6 themes', () => {
    expect(THEMES).toHaveLength(6);
  });

  it('has 3 dark and 3 light', () => {
    expect(THEMES.filter((t) => t.mode === 'dark')).toHaveLength(3);
    expect(THEMES.filter((t) => t.mode === 'light')).toHaveLength(3);
  });
});

describe('getThemeById', () => {
  it('finds obsidian', () => {
    const t = getThemeById('obsidian');
    expect(t?.label).toBe('Obsidian');
    expect(t?.mode).toBe('dark');
  });

  it('returns undefined for unknown id', () => {
    expect(getThemeById('nonexistent')).toBeUndefined();
  });
});
