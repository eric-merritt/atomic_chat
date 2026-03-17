import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { ToolCategory } from '../atoms/tool';
import { fetchTools as apiFetchTools, toggleTool as apiToggleTool, toggleCategory as apiToggleCategory } from '../api/tools';

interface ToolContextValue {
  categories: ToolCategory[];
  selected: string[];
  toggleTool: (name: string) => Promise<void>;
  toggleCategory: (name: string) => Promise<void>;
}

export const ToolContext = createContext<ToolContextValue | null>(null);

function getSelected(categories: ToolCategory[]): string[] {
  return categories.flatMap((c) => c.tools.filter((t) => t.selected).map((t) => t.name));
}

export function ToolProvider({ children }: { children: ReactNode }) {
  const [categories, setCategories] = useState<ToolCategory[]>([]);

  useEffect(() => {
    apiFetchTools().then((r) => { if (r.data) setCategories(r.data); }).catch(() => {});
  }, []);

  const toggleTool = useCallback(async (name: string) => {
    const r = await apiToggleTool(name);
    if (r.data) setCategories(r.data);
  }, []);

  const toggleCategory = useCallback(async (name: string) => {
    const r = await apiToggleCategory(name);
    if (r.data) setCategories(r.data);
  }, []);

  return (
    <ToolContext.Provider value={{ categories, selected: getSelected(categories), toggleTool, toggleCategory }}>
      {children}
    </ToolContext.Provider>
  );
}
