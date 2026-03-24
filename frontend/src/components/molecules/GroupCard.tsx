import { useState } from 'react';
import type { WorkflowTool } from '../../api/workflowGroups';

interface GroupCardProps {
  name: string;
  tooltip: string;
  tools: WorkflowTool[];
  active: boolean;
  onOpen: (name: string) => void;
  onClose: (name: string) => void;
}

export function GroupCard({ name, tooltip, tools, active, onOpen, onClose }: GroupCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`rounded-lg border transition-colors ${
        active
          ? 'border-[var(--accent)] shadow-[0_0_8px_color-mix(in_srgb,var(--accent)_40%,transparent)]'
          : 'border-[var(--glass-border)] hover:border-[var(--accent)]'
      } bg-[var(--glass-bg-solid)]`}
    >
      <div className="flex items-center">
        <button
          className="flex items-center justify-center w-8 h-full shrink-0 cursor-pointer hover:bg-[var(--glass-highlight)] rounded-l-lg transition-colors"
          onClick={(e) => { e.stopPropagation(); setExpanded((p) => !p); }}
          title="Show tools"
        >
          <span className={`text-[var(--text-muted)] text-xs transition-transform ${expanded ? 'rotate-45' : ''}`}>
            ⊞
          </span>
        </button>

        <button
          className="flex-1 flex items-center gap-2 px-2 py-2.5 cursor-pointer text-left min-w-0"
          onClick={() => onOpen(name)}
        >
          <div className="flex-1 min-w-0">
            <span className="text-sm font-medium text-[var(--text)] block truncate">{name}</span>
            <span className="text-[10px] text-[var(--text-muted)] block truncate">{tooltip}</span>
          </div>
          <span className="text-xs font-mono text-[var(--text-muted)] shrink-0">{tools.length}</span>
        </button>

        {active && (
          <button
            className="flex items-center justify-center w-6 h-6 mr-1 shrink-0 cursor-pointer text-[var(--text-muted)] hover:text-[#ff2020] transition-colors"
            onClick={(e) => { e.stopPropagation(); onClose(name); }}
            title="Remove group"
          >
            &times;
          </button>
        )}
      </div>

      {expanded && (
        <div className="border-t border-[var(--glass-border)] px-3 py-1.5">
          <div className="flex flex-wrap gap-1">
            {tools.map((t) => (
              <span
                key={t.name}
                className="text-[10px] font-mono text-[var(--accent)] px-1.5 py-0.5 rounded bg-[var(--glass-highlight)]"
              >
                {t.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
