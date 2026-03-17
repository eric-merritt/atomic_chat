import { createContext, useState, useEffect, type ReactNode } from 'react';
import { THEMES, getThemeById, type Theme } from '../atoms/theme';

interface ThemeContextValue {
  theme: Theme;
  setTheme: (id: string) => void;
  themes: Theme[];
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = 'agentic-theme';
const DEFAULT_THEME = THEMES[0];

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return (saved && getThemeById(saved)) || DEFAULT_THEME;
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme.id);
  }, [theme]);

  const setTheme = (id: string) => {
    const t = getThemeById(id);
    if (t) {
      setThemeState(t);
      localStorage.setItem(STORAGE_KEY, id);
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  );
}
