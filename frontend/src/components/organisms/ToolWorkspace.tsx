import { useState, useCallback } from 'react';
import { useWorkspace } from '../../hooks/useWorkspace';
import { ToolButton } from '../atoms/ToolButton';
import { ParamTable } from '../molecules/ParamTable';
import type { WorkflowTool } from '../../api/workflowGroups';

export function ToolWorkspace() {
  const { groups, activeGroups, closeGroup, selectedTool, selectTool } = useWorkspace();
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
    if (found) { selectedToolData = found; break; }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[var(--bg-base)]">
      <div className="flex-1 overflow-y-auto">
        {activeGroupData.map((g) => (
          <div key={g.name} className="border-b border-[var(--glass-border)]">
            {/* Group header */}
            <div className="flex items-center px-4 py-2 bg-[var(--glass-bg-solid)]">
              <span className="flex-1 text-sm font-semibold text-[var(--text)]">{g.name}</span>
              <button
                className="text-[var(--text-muted)] hover:text-[#ff2020] cursor-pointer transition-colors text-sm"
                onClick={() => closeGroup(g.name)}
                title="Close group"
              >
                &times;
              </button>
            </div>

            {/* Tool buttons */}
            <div className="flex flex-wrap gap-2 px-4 py-3">
              {g.tools.map((t) => (
                <ToolButton
                  key={t.name}
                  name={t.name}
                  selected={selectedTool === t.name}
                  onClick={() => selectTool(selectedTool === t.name ? null : t.name)}
                />
              ))}
            </div>

            {/* Tool detail (if a tool in this group is selected) */}
            {selectedToolData && g.tools.some((t) => t.name === selectedTool) && (
              <div className="px-4 pb-4 border-t border-[var(--glass-border)]">
                <div className="flex items-center justify-between py-2">
                  <span className="text-xs font-mono text-[var(--accent)]">{selectedToolData.name}</span>
                  <div className="flex items-center gap-2">
                    <button
                      className="text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer transition-colors"
                      onClick={() => setInteractive((p) => !p)}
                    >
                      {interactive ? 'Read-only' : 'Interactive'}
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
                <p className="text-[10px] text-[var(--text-muted)] mb-2">{selectedToolData.description}</p>
                <ParamTable
                  params={selectedToolData.params}
                  interactive={interactive}
                  values={paramValues}
                  onChange={handleParamChange}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
