import {
  createContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";

import { useLocation } from "react-router-dom";

import {
  fetchWorkflowGroups,
  selectGroup,
  type WorkflowGroup,
} from "../api/workflowGroups";
import { useTools } from "../hooks/useTools";
import type { ApGalleryPayload } from "../components/organisms/ApGallery";
import { filterStopWords } from "../lib/stopWords";

export type LayoutState = "default" | "workspace-chat" | "workspace-inputbar";

const NODE_COLORS: Record<string, { bg: string; border: string }> = {
  Root: { bg: "#64748b", border: "#475569" },
  Directory: { bg: "#3b82f6", border: "#2563eb" },
  DependencyList: { bg: "#78716c", border: "#57534e" },
  Class: { bg: "#8b5cf6", border: "#7c3aed" },
  Function: { bg: "#10b981", border: "#059669" },
  File: { bg: "#f59e0b", border: "#d97706" },
  Import: { bg: "#71717a", border: "#52525b" },
  State: { bg: "#f43f5e", border: "#e11d48" },
  Prop: { bg: "#d946ef", border: "#c026d3" },
  Rule: { bg: "#06b6d4", border: "#0891b2" },
};

const EDGE_COLORS: Record<string, string> = {
  CONTAINS: "#4b5563",
  DEPENDS_ON: "#06b6d4",
  CALLS: "#3b82f6",
  IMPLEMENTS_REQUIRED_METHOD: "#f97316",
  TRACKS: "#ec4899",
};

const NODE_SHAPES: Record<string, string> = {
  Root: "octagon",
  Directory: "roundrectangle",
  DependencyList: "ellipse",
  Class: "hexagon",
  Function: "ellipse",
  File: "rectangle",
  Import: "triangle",
  State: "diamond",
  Prop: "diamond",
  Rule: "roundrectangle",
};

export interface DependencyListItem {
  id: string;
  name?: string;
  code?: string;
  file?: string;
  language?: string;
  line_start?: number;
  line_end?: number;
  [key: string]: unknown;
}

interface GraphVizNode {
  id: string;
  type: string;
  label: string;
  file?: string;
  path?: string;
  language?: string;
  summary?: string;
  dependencies?: DependencyListItem[];
  line_start?: number;
  line_end?: number;
}

interface GraphVizData {
  nodes: GraphVizNode[];
  edges: { id: string; source: string; target: string; type: string }[];
}

interface GraphScoredTool {
  name: string;
  category: string;
  summary: string;
  call_summary: string;
  score: number;
}

interface WorkspaceContextValue {
  layout: LayoutState;
  setLayout: (layout: LayoutState) => void;
  groups: WorkflowGroup[];
  activeGroups: string[];
  toggleGroup: (name: string) => Promise<void>;
  refreshGroups: () => Promise<void>;
  selectedTool: string | null;
  selectTool: (name: string | null) => void;
  galleryPayload: ApGalleryPayload | null;
  showGallery: (payload: ApGalleryPayload) => void;
  clearGallery: () => void;
  accountingOpen: boolean;
  openAccounting: () => void;
  closeAccounting: () => void;
  // Graph
  graphData: GraphVizData | null;
  graphLoading: boolean;
  graphExcludedTypes: Set<string>;
  graphToggleExcludedType: (v: string) => void;
  graphVizDepth: number;
  graphSetVizDepth: (v: number) => void;
  graphSearch: string;
  graphSearchInput: string;
  graphSetSearchInput: (v: string) => void;
  graphSearchLoading: boolean;
  graphClearSearch: () => void;
  graphHighlightCount: number;
  graphHighlightIds: Set<string>;
  graphTaskQuery: string;
  graphSetTaskQuery: (v: string) => void;
  graphMatchedTools: GraphScoredTool[];
  graphToolLoading: boolean;
  graphReload: () => void;
  NODE_COLORS: Record<string, { bg: string; border: string }>;
  EDGE_COLORS: Record<string, string>;
  NODE_SHAPES: Record<string, string>;
  location: string;
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(
  null,
);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { refreshTools } = useTools();
  const [groups, setGroups] = useState<WorkflowGroup[]>([]);
  const [activeGroups, setActiveGroups] = useState<string[]>([]);
  const [layout, setLayout] = useState<LayoutState>("default");
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [galleryPayload, setGalleryPayload] = useState<ApGalleryPayload | null>(
    null,
  );
  const [accountingOpen, setAccountingOpen] = useState(false);

  // Graph state
  const [graphData, setGraphData] = useState<GraphVizData | null>(null);
  const [graphLoading, setGraphLoading] = useState(true);
  const [graphExcludedTypes, setGraphExcludedTypes] = useState<Set<string>>(
    new Set(),
  );
  const [graphVizDepth, setGraphVizDepth] = useState(1);
  const [graphSearch, setGraphSearch] = useState("");
  const [graphSearchInput, setGraphSearchInput] = useState("");
  const [graphSearchLoading, setGraphSearchLoading] = useState(false);
  const [graphTaskQuery, setGraphTaskQuery] = useState("");
  const [graphMatchedTools, setGraphMatchedTools] = useState<GraphScoredTool[]>(
    [],
  );
  const [graphToolLoading, setGraphToolLoading] = useState(false);
  const [graphHighlightIds, setGraphHighlightIds] = useState<Set<string>>(
    new Set(),
  );
  const location = useLocation().pathname;
  const loadGroups = useCallback(async () => {
    try {
      const r = await fetchWorkflowGroups();
      setGroups(r.groups);
    } catch (e: unknown) {
      console.error(
        "[WorkspaceProvider] Failed to load workflow groups —",
        e instanceof Error ? e.message : String(e),
      );
    }
  }, []);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    if (location === "/graph") setLayout("workspace-chat");
  }, [location]);
  const toggleGroup = useCallback(
    async (name: string) => {
      let willBeActive = false;
      setActiveGroups((prev) => {
        if (prev.includes(name)) {
          const next = prev.filter((g) => g !== name);
          if (next.length === 0) setLayout("default");
          willBeActive = false;
          return next;
        }
        willBeActive = true;
        return [...prev, name];
      });
      if (willBeActive) {
        setLayout((prev) => (prev === "default" ? "workspace-chat" : prev));
      }
      try {
        await selectGroup(name, willBeActive);
        await refreshTools();
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        console.error(
          `[WorkspaceProvider] Failed to sync group "${name}" with backend — UI state preserved:`,
          msg,
        );
      }
    },
    [refreshTools],
  );

  const selectToolCb = useCallback((name: string | null) => {
    setSelectedTool(name);
  }, []);

  const showGallery = useCallback((payload: ApGalleryPayload) => {
    setGalleryPayload(payload);
    setLayout((prev) => (prev === "default" ? "workspace-chat" : prev));
  }, []);

  const clearGallery = useCallback(() => {
    setGalleryPayload(null);
    setLayout((prev) =>
      prev === "workspace-chat" && activeGroups.length === 0 ? "default" : prev,
    );
  }, [activeGroups.length]);

  // Graph data fetching
  const fetchGraph = useCallback(async (_type: string, depth: number) => {
    setGraphLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("depth", String(depth));
      const res = await fetch(`/api/graph/viz?${params}`);
      const json: GraphVizData = await res.json();
      setGraphData(json);
    } catch (e) {
      console.error("Failed to fetch graph:", e);
    } finally {
      setGraphLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGraph("all", graphVizDepth);
  }, [graphVizDepth, fetchGraph]);

  // Graph search → highlight (debounced live update)
  useEffect(() => {
    if (!graphData) return;

    const trimmed = graphSearchInput.trim();
    if (!trimmed) {
      setGraphSearch("");
      setGraphHighlightIds(new Set());
      setGraphSearchLoading(false);
      return;
    }

    setGraphSearchLoading(true);
    const timer = setTimeout(() => {
      setGraphSearch(trimmed);
      setGraphSearchLoading(false);
    }, 300);

    return () => clearTimeout(timer);
  }, [graphSearchInput, graphData]);

  useEffect(() => {
    if (!graphData) return;
    if (!graphSearch.trim()) {
      setGraphHighlightIds(new Set());
      return;
    }
    const tokens = filterStopWords(graphSearch.toLowerCase().split(/\s+/));
    const matched = new Set<string>();
    graphData.nodes.forEach((n) => {
      const haystack = [n.label, n.summary || "", n.file || ""]
        .join(" ")
        .toLowerCase();
      if (tokens.some((t) => haystack.includes(t))) {
        matched.add(n.id);
      }
    });
    setGraphHighlightIds(matched);
  }, [graphSearch, graphData]);

  const graphClearSearch = useCallback(() => {
    setGraphSearchInput("");
    setGraphSearch("");
  }, []);

  // Tool routing → live debounced
  useEffect(() => {
    if (!graphData) return;

    const trimmed = graphTaskQuery.trim();
    if (!trimmed) {
      setGraphMatchedTools([]);
      setGraphHighlightIds(new Set());
      setGraphToolLoading(false);
      return;
    }

    setGraphToolLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await fetch("/api/graph/route-tools", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description: trimmed, limit: 15 }),
        });
        const json = await res.json();
        setGraphMatchedTools(json.tools || []);
        const toolSet = new Set(
          (json.tools || []).map((t: GraphScoredTool) => t.name),
        );
        const toolIds = new Set<string>();
        graphData?.nodes.forEach((n) => {
          if (n.type === "Class" && toolSet.has(n.label)) toolIds.add(n.id);
        });
        setGraphHighlightIds(toolIds);
      } catch (e) {
        console.error("Tool routing failed:", e);
      } finally {
        setGraphToolLoading(false);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [graphTaskQuery, graphData]);

  const graphReload = useCallback(() => {
    fetch("/api/graph/reload", { method: "POST" }).then(() =>
      fetchGraph("all", graphVizDepth),
    );
  }, [fetchGraph, graphVizDepth]);

  const graphToggleExcludedType = useCallback((type: string) => {
    setGraphExcludedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  return (
    <WorkspaceContext.Provider
      value={{
        location,
        layout,
        setLayout,
        groups,
        activeGroups,
        toggleGroup,
        refreshGroups: loadGroups,
        selectedTool,
        selectTool: selectToolCb,
        galleryPayload,
        showGallery,
        clearGallery,
        accountingOpen,
        openAccounting: () => setAccountingOpen(true),
        closeAccounting: () => setAccountingOpen(false),
        // Graph
        graphData,
        graphLoading,
        graphExcludedTypes,
        graphToggleExcludedType,
        graphVizDepth,
        graphSetVizDepth: setGraphVizDepth,
        graphSearch,
        graphSearchInput,
        graphSetSearchInput: setGraphSearchInput,
        graphSearchLoading,
        graphClearSearch,
        graphHighlightCount: graphHighlightIds.size,
        graphHighlightIds,
        graphTaskQuery,
        graphSetTaskQuery: setGraphTaskQuery,
        graphMatchedTools,
        graphToolLoading,
        graphReload,
        NODE_COLORS,
        EDGE_COLORS,
        NODE_SHAPES,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}
