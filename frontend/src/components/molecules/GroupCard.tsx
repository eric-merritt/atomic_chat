import { useState } from 'react';
import type { WorkflowTool } from '../../api/workflowGroups';

interface GroupCardProps {
  name: string;
  tooltip: string;
  tools: WorkflowTool[];
  active: boolean;
  onToggle: (name: string) => void;
}

export function GroupCard({ name, tooltip, tools, active, onToggle }: GroupCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onToggle(name)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onToggle(name);
        }
      }}
      className={`rounded-lg border transition-colors cursor-pointer ${
        active
          ? 'border-[var(--accent)] shadow-[0_0_8px_color-mix(in_srgb,var(--accent)_40%,transparent)]'
          : 'border-[var(--glass-border)] hover:border-[var(--accent)]'
      } bg-[var(--glass-bg-solid)]`}
    >
      <div className="flex items-center">
        <button
          type="button"
          className="flex items-center justify-center w-8 h-full shrink-0 cursor-pointer hover:bg-[var(--glass-highlight)] rounded-l-lg transition-colors"
          onClick={(e) => { e.stopPropagation(); setExpanded((p) => !p); }}
          title={expanded ? 'Hide tools' : 'Show tools'}
        >
          <span className={`text-[var(--text-muted)] text-xs transition-transform ${expanded ? 'rotate-45' : ''}`}>
            ⊞
          </span>
        </button>

        <div className="flex-1 flex items-center gap-2 px-2 py-2.5 text-left min-w-0">
          <div className="flex-1 min-w-0">
            <span className="text-sm font-medium text-[var(--text)] block truncate">{name}</span>
            <span className="text-[10px] text-[var(--text-muted)] block truncate">{tooltip}</span>
          </div>
          <span className="text-xs font-mono text-[var(--text-muted)] shrink-0">{tools.length}</span>
        </div>
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
