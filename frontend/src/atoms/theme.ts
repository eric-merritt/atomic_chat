export type ThemeMode = 'dark' | 'light';

export interface Theme {
  id: string;
  label: string;
  mode: ThemeMode;
}

export const THEMES: Theme[] = [
  { id: 'obsidian', label: 'Obsidian', mode: 'dark' },
  { id: 'carbon', label: 'Carbon', mode: 'dark' },
  { id: 'amethyst', label: 'Amethyst', mode: 'dark' },
  { id: 'frost', label: 'Frost', mode: 'light' },
  { id: 'sand', label: 'Sand', mode: 'light' },
  { id: 'blossom', label: 'Blossom', mode: 'light' },
];

export function getThemeById(id: string): Theme | undefined {
  return THEMES.find((t) => t.id === id);
}
