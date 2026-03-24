import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { fetchWorkflowGroups, selectGroup, type WorkflowGroup } from '../api/workflowGroups';
import { useTools } from '../hooks/useTools';

export type LayoutState = 'default' | 'workspace-chat' | 'workspace-inputbar';

interface WorkspaceContextValue {
  layout: LayoutState;
  setLayout: (layout: LayoutState) => void;
  groups: WorkflowGroup[];
  activeGroups: string[];
  openGroup: (name: string) => Promise<void>;
  closeGroup: (name: string) => Promise<void>;
  selectedTool: string | null;
  selectTool: (name: string | null) => void;
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { refreshTools } = useTools();
  const [groups, setGroups] = useState<WorkflowGroup[]>([]);
  const [activeGroups, setActiveGroups] = useState<string[]>([]);
  const [layout, setLayout] = useState<LayoutState>('default');
  const [selectedTool, setSelectedTool] = useState<string | null>(null);

  useEffect(() => {
    fetchWorkflowGroups()
      .then((r) => setGroups(r.groups))
      .catch(() => {});
  }, []);

  const openGroup = useCallback(async (name: string) => {
    setActiveGroups((prev) => (prev.includes(name) ? prev : [...prev, name]));
    setLayout((prev) => (prev === 'default' ? 'workspace-chat' : prev));
    try {
      await selectGroup(name, true);
      await refreshTools();
    } catch (e) {
      console.error('Failed to activate group:', e);
    }
  }, [refreshTools]);

  const closeGroup = useCallback(async (name: string) => {
    setActiveGroups((prev) => {
      const next = prev.filter((g) => g !== name);
      if (next.length === 0) setLayout('default');
      return next;
    });
    try {
      await selectGroup(name, false);
      await refreshTools();
    } catch (e) {
      console.error('Failed to deactivate group:', e);
    }
  }, [refreshTools]);

  const selectToolCb = useCallback((name: string | null) => {
    setSelectedTool(name);
  }, []);

  return (
    <WorkspaceContext.Provider
      value={{
        layout, setLayout, groups, activeGroups,
        openGroup, closeGroup, selectedTool, selectTool: selectToolCb,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}
