import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import coseBilkent from "cytoscape-cose-bilkent";
import { useWorkspace } from "../../hooks/useWorkspace";
import type { DependencyListItem } from "../../providers/WorkspaceProvider";

cytoscape.use(coseBilkent);

/* ── Canvas ──────────────────────────────────────────────────────────── */

export function GraphCanvas() {
  const {
    graphData,
    graphLoading,
    graphSearch,
    graphHighlightIds,
    graphExcludedTypes,
    NODE_COLORS,
    EDGE_COLORS,
    NODE_SHAPES,
  } = useWorkspace();
  const cyRef = useRef<HTMLDivElement | null>(null);
  const cyInstance = useRef<cytoscape.Core | null>(null);
  const [selectedNode, setSelectedNode] = useState<{
    label: string;
    type: string;
    path?: string;
    line_start?: number;
    line_end?: number;
    summary?: string;
    dependencies?: DependencyListItem[];
  } | null>(null);

  // Init cytoscape
  useEffect(() => {
    if (!graphData || !cyRef.current) return;

    const visibleNodeIds = new Set<string>();
    const visibleNodes = graphData.nodes.filter((n) => {
      if (graphExcludedTypes.has(n.type)) return false;
      visibleNodeIds.add(n.id);
      return true;
    });
    const visibleEdges = graphData.edges.filter(
      (e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target),
    );

    const elements = [
      ...visibleNodes.map((n) => ({
        data: {
          id: n.id,
          label: n.label,
          type: n.type,
          file: n.file || "",
          path: n.path || "",
          summary: n.summary || "",
          dependencies: (n as unknown as Record<string, unknown>).dependencies as
            | Array<Record<string, unknown>>
            | null,
        },
      })),
      ...visibleEdges.map((e) => ({
        data: { id: e.id, source: e.source, target: e.target, type: e.type },
      })),
    ];
    if (cyInstance.current) cyInstance.current.destroy();

    const cy = cytoscape({
      container: cyRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            label: (el: cytoscape.NodeSingular) => {
              const t = el.data("type");
              if (t === "DependencyList") {
                const deps = el.data("dependencies");
                let count = 0;
                if (Array.isArray(deps)) count = deps.length;
                else if (typeof deps === "string") {
                  try {
                    const parsed = JSON.parse(deps);
                    count = Array.isArray(parsed) ? parsed.length : 0;
                  } catch {
                    count = 0;
                  }
                }
                return `${count} deps`;
              }
              const label = el.data("label") || "";
              return label.length > 20 ? label.slice(0, 18) + "…" : label;
            },
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "9px",
            color: "#e5e7eb",
            "text-wrap": "wrap",
            "text-max-width": "80px",
            "background-color": (el: cytoscape.NodeSingular) =>
              NODE_COLORS[el.data("type") as string]?.bg || "#9ca3af",
            "border-color": (el: cytoscape.NodeSingular) =>
              NODE_COLORS[el.data("type") as string]?.border || "#6b7280",
            "border-width": 2,
            width: (el: cytoscape.NodeSingular) => {
              const t = el.data("type");
              if (t === "Directory") return 80;
              if (t === "Root") return 70;
              return 60;
            },
            height: (el: cytoscape.NodeSingular) => {
              const t = el.data("type");
              if (t === "Directory" || t === "Root" || t === "DependencyList") return 50;
              return 40;
            },
          },
        },
        ...Object.entries(NODE_SHAPES).map(([t, s]) => ({
          selector: `node[type = "${t}"]`,
          style: { shape: s },
        })),
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": (el: cytoscape.EdgeSingular) =>
              EDGE_COLORS[el.data("type") as string] || "#9ca3af",
            "target-arrow-color": (el: cytoscape.EdgeSingular) =>
              EDGE_COLORS[el.data("type") as string] || "#9ca3af",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(type)",
            "font-size": "8px",
            color: "#d1d5db",
            "text-rotation": "autorotate",
            "text-margin-y": -8,
          },
        },
        {
          selector: ".highlighted",
          style: {
            "border-width": 4,
            "border-color": "#fbbf24",
            "background-color": "#fbbf24",
          },
        },
        { selector: ".dimmed", style: { opacity: 0.15 } },
      ] as unknown as cytoscape.StylesheetCSS[],
      layout: {
        name: "cose-bilkent",
        nodeRepulsion: 4500,
        idealEdgeLength: 80,
        edgeElasticity: 0.45,
        nestingFactor: 0.1,
        gravity: 0.25,
        numIter: 2500,
        initialEnergyOnIncremental: 0.3,
      } as cytoscape.LayoutOptions,
    });

    cy.on("tap", "node", (evt) => {
      const nd = graphData.nodes.find((n) => n.id === evt.target.id()) || null;
      setSelectedNode(nd);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) setSelectedNode(null);
    });
    cyInstance.current = cy;
    return () => {
      cy.destroy();
      cyInstance.current = null;
    };
  }, [graphData, graphExcludedTypes]);

  // Apply highlights from pre-computed search results
  useEffect(() => {
    if (!cyInstance.current || !graphData) return;
    const cy = cyInstance.current;
    cy.elements().removeClass("dimmed highlighted");
    if (!graphSearch.trim()) return;
    cy.nodes().forEach((node) => {
      graphHighlightIds.has(node.id())
        ? node.addClass("highlighted")
        : node.addClass("dimmed");
    });
    cy.edges().addClass("dimmed");
  }, [graphSearch, graphHighlightIds, graphData]);

  return (
    <div className="relative overflow-hidden bg-[var(--bg-base)]">
      {graphLoading && (
        <div className="absolute inset-0 flex items-center justify-center z-10 bg-[var(--bg-base)]/80">
          <span className="text-sm text-[var(--text-muted)]">
            Loading graph...
          </span>
        </div>
      )}
      <div ref={cyRef} className="w-full h-full" />

      {selectedNode && (
        <div className="absolute bottom-4 right-4 w-72 max-h-56 overflow-y-auto rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-solid)] backdrop-blur-md shadow-lg p-3">
          <div className="flex items-center justify-between mb-1.5">
            <h3 className="text-sm font-semibold text-[var(--text)]">
              {selectedNode.label}
            </h3>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-[var(--text-muted)] hover:text-[var(--text)] cursor-pointer"
            >
              ✕
            </button>
          </div>
          <div className="space-y-1 text-xs">
            <div>
              <span className="text-[var(--text-muted)]">Type: </span>
              <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-[var(--input-bg)] text-[var(--text)]">
                {selectedNode.type}
              </span>
            </div>
            {selectedNode.path && (
              <div>
                <span className="text-[var(--text-muted)]">Path: </span>
                <span className="text-[var(--text-secondary)]">
                  {selectedNode.path}
                </span>
              </div>
            )}
            {selectedNode.line_start != null && (
              <div>
                <span className="text-[var(--text-muted)]">Lines: </span>
                <span className="text-[var(--text-secondary)]">
                  {selectedNode.line_start}–{selectedNode.line_end}
                </span>
              </div>
            )}
            {selectedNode.summary && (
              <div className="mt-1.5">
                <span className="text-[var(--text-muted)]">Summary: </span>
                <p className="text-[var(--text-secondary)] mt-0.5">
                  {selectedNode.summary}
                </p>
              </div>
            )}
            {(() => {
              let deps = selectedNode.dependencies;
              if (typeof deps === "string") {
                try { deps = JSON.parse(deps); } catch { deps = undefined; }
              }
              if (deps && deps.length > 0) {
                return (
                  <div className="mt-1.5 space-y-1">
                    <div className="text-[var(--text-muted)]">Dependencies ({deps.length})</div>
                    <div className="max-h-32 overflow-y-auto space-y-0.5">
                      {deps.map((d: DependencyListItem, i: number) => (
                        <div key={i} className="px-1.5 py-0.5 rounded bg-[var(--input-bg)] text-[var(--text-secondary)] text-[10px]">
                          {String(d.code || d.name || d.id)}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              }
              return null;
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
