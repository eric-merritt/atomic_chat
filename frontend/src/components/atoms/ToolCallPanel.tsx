import { useState } from 'react';

export interface ToolActivity {
  type: 'call' | 'result';
  tool: string;
  content: string;
  timestamp: number;
}

interface ToolCallPanelProps {
  activities: ToolActivity[];
}

export function ToolCallPanel({ activities }: ToolCallPanelProps) {
  const [expanded, setExpanded] = useState(false);

  if (activities.length === 0) return null;

  return (
    <div
      className="self-start w-[75%] rounded-xl overflow-hidden transition-all duration-300"
      style={{
        border: '1px solid color-mix(in srgb, var(--accent) 30%, transparent)',
        background: 'color-mix(in srgb, var(--msg-assistant) 60%, transparent)',
        maxHeight: expanded ? '28rem' : '6rem',
      }}
    >
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-xs font-mono text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors cursor-pointer"
      >
        <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
        <span>Tools ({activities.length})</span>
        <span className="ml-auto text-[10px]">{expanded ? '\u25B2' : '\u25BC'}</span>
      </button>

      <div
        className="overflow-y-auto px-3 pb-2"
        style={{ maxHeight: expanded ? '26rem' : '3.5rem' }}
      >
        {activities.map((a, i) => (
          <div key={i} className="flex gap-2 py-0.5 text-xs font-mono leading-snug">
            <span
              className="shrink-0"
              style={{ color: a.type === 'call' ? 'var(--accent)' : 'var(--text-muted)' }}
            >
              {a.type === 'call' ? '\u25B6' : '\u25C0'}
            </span>
            <span className="shrink-0 font-semibold text-[var(--accent)]">{a.tool}</span>
            <span className="text-[var(--text-muted)] truncate">{a.content}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
