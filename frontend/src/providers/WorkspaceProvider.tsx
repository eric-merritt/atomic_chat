import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { fetchWorkflowGroups, selectGroup, type WorkflowGroup } from '../api/workflowGroups';
import { useTools } from '../hooks/useTools';
import type { ApGalleryPayload } from '../components/organisms/ApGallery';

export type LayoutState = 'default' | 'workspace-chat' | 'workspace-inputbar';

interface WorkspaceContextValue {
  layout: LayoutState;
  setLayout: (layout: LayoutState) => void;
  groups: WorkflowGroup[];
  activeGroups: string[];
  toggleGroup: (name: string) => Promise<void>;
  selectedTool: string | null;
  selectTool: (name: string | null) => void;
  galleryPayload: ApGalleryPayload | null;
  showGallery: (payload: ApGalleryPayload) => void;
  clearGallery: () => void;
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { refreshTools } = useTools();
  const [groups, setGroups] = useState<WorkflowGroup[]>([]);
  const [activeGroups, setActiveGroups] = useState<string[]>([]);
  const [layout, setLayout] = useState<LayoutState>('default');
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [galleryPayload, setGalleryPayload] = useState<ApGalleryPayload | null>(null);

  useEffect(() => {
    fetchWorkflowGroups()
      .then((r) => setGroups(r.groups))
      .catch((e: unknown) => {
        console.error(
          '[WorkspaceProvider] Failed to load workflow groups from /api/workspace/groups —',
          e instanceof Error ? e.message : String(e)
        );
      });
  }, []);

  const toggleGroup = useCallback(async (name: string) => {
    let willBeActive = false;
    setActiveGroups((prev) => {
      if (prev.includes(name)) {
        const next = prev.filter((g) => g !== name);
        if (next.length === 0) setLayout('default');
        willBeActive = false;
        return next;
      }
      willBeActive = true;
      return [...prev, name];
    });
    if (willBeActive) {
      setLayout((prev) => (prev === 'default' ? 'workspace-chat' : prev));
    }
    try {
      await selectGroup(name, willBeActive);
      await refreshTools();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(`[WorkspaceProvider] Failed to sync group "${name}" with backend — UI state preserved:`, msg);
    }
  }, [refreshTools]);

  const selectToolCb = useCallback((name: string | null) => {
    setSelectedTool(name);
  }, []);

  const showGallery = useCallback((payload: ApGalleryPayload) => {
    setGalleryPayload(payload);
    setLayout((prev) => (prev === 'default' ? 'workspace-chat' : prev));
  }, []);

  const clearGallery = useCallback(() => {
    setGalleryPayload(null);
    setLayout((prev) => (prev === 'workspace-chat' && activeGroups.length === 0 ? 'default' : prev));
  }, [activeGroups.length]);

  return (
    <WorkspaceContext.Provider
      value={{
        layout, setLayout, groups, activeGroups,
        toggleGroup, selectedTool, selectTool: selectToolCb,
        galleryPayload, showGallery, clearGallery,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}
