import { useState, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { useWorkspace } from "../../hooks/useWorkspace";
import { ToolButton } from "../atoms/ToolButton";
import { ParamTable } from "../molecules/ParamTable";
import { AccountingWorkspace } from "./AccountingWorkspace";
import type { WorkflowTool } from "../../api/workflowGroups";
import { GraphCanvas } from "./GraphCanvas";

export function Workspace() {
  const { pathname } = useLocation();
  if (pathname === "/graph") {
    return <GraphCanvas />;
  }

  return <WorkspaceInner />;
}

function WorkspaceInner() {
  const {
    groups,
    activeGroups,
    selectedTool,
    selectTool,
    accountingOpen,
    openAccounting,
  } = useWorkspace();
  const [interactive, setInteractive] = useState(false);
  const [paramValues, setParamValues] = useState<Record<string, unknown>>({});

  const activeGroupData = groups.filter((g) => activeGroups.includes(g.name));

  const handleParamChange = useCallback((name: string, value: unknown) => {
    setParamValues((prev) => ({ ...prev, [name]: value }));
  }, []);

  // Find the selected tool's full data
  let selectedToolData: WorkflowTool | null = null;
  for (const g of activeGroupData) {
    const found = g.tools.find((t) => t.name === selectedTool);
    if (found) {
      selectedToolData = found;
      break;
    }
  }
  const location = useLocation().pathname;

  if (accountingOpen) return <AccountingWorkspace />;

  return (
    <div
      id="toolWorkspace"
      className="flex flex-col h-full overflow-hidden bg-[var(--bg-base)]"
    >
      <div className="flex-1 overflow-y-auto">
        {location == "/graph" ? (
          <GraphCanvas />
        ) : (
          activeGroupData.map((g) => (
            <div key={g.name} className="border-b border-[var(--glass-border)]">
              {/* Group header */}
              <div className="flex items-center px-4 py-2 bg-[var(--glass-bg-solid)]">
                <span className="flex-1 text-sm font-semibold text-[var(--text)]">
                  {g.name}
                </span>
                {g.name === "Accounting" && (
                  <button
                    onClick={openAccounting}
                    className="text-[10px] font-mono uppercase tracking-widest px-2 py-0.5
                    border border-[var(--accent)] text-[var(--accent)] rounded
                    hover:bg-[var(--accent)] hover:text-[var(--bg-base)] transition-colors cursor-pointer"
                  >
                    Open Ledger
                  </button>
                )}
              </div>

              {/* Tool buttons */}
              <div className="flex flex-wrap gap-2 px-4 py-3">
                {g.tools.map((t) => (
                  <ToolButton
                    key={t.name}
                    name={t.name}
                    selected={selectedTool === t.name}
                    onClick={() =>
                      selectTool(selectedTool === t.name ? null : t.name)
                    }
                  />
                ))}
              </div>

              {/* Tool detail (if a tool in this group is selected) */}
              {selectedToolData &&
                g.tools.some((t) => t.name === selectedTool) && (
                  <div className="px-4 pb-4 border-t border-[var(--glass-border)]">
                    <div className="flex items-center justify-between py-2">
                      <span className="text-xs font-mono text-[var(--accent)]">
                        {selectedToolData.name}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          className="text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer transition-colors"
                          onClick={() => setInteractive((p) => !p)}
                        >
                          {interactive ? "Read-only" : "Interactive"}
                        </button>
                        {/* Push to chain — disabled for Layer 1 */}
                        <button
                          className="text-[10px] text-[var(--text-muted)] opacity-50 cursor-not-allowed"
                          title="Chain view coming soon"
                          disabled
                        >
                          Chain
                        </button>
                      </div>
                    </div>
                    <p className="text-[10px] text-[var(--text-muted)] mb-2">
                      {selectedToolData.description}
                    </p>
                    <ParamTable
                      params={selectedToolData.params}
                      interactive={interactive}
                      values={paramValues}
                      onChange={handleParamChange}
                    />
                  </div>
                )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
