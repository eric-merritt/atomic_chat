// Ring fills to 100% when context reaches TRIGGER_PCT. Clicking manually summarizes.
const TRIGGER_PCT = 75;

interface ContextRingProps {
  contextPct: number;
  summarizing: boolean;
  onSummarize: () => void;
}

export function ContextRing({ contextPct, summarizing, onSummarize }: ContextRingProps) {
  const fill = Math.min(contextPct / TRIGGER_PCT, 1);
  const r = 12;
  const size = 32;
  const circumference = 2 * Math.PI * r;
  const dashoffset = circumference * (1 - fill);

  const strokeColor =
    fill >= 1 ? 'var(--danger, #ef4444)'
    : fill >= 0.7 ? '#f59e0b'
    : 'var(--accent)';

  return (
    <button
      onClick={onSummarize}
      disabled={summarizing}
      title={contextPct < 1 ? 'Context empty' : `Context: ${Math.round(contextPct)}% — ${fill >= 1 ? 'click to summarize' : `auto-summarizes at ${TRIGGER_PCT}%`}`}
      className="shrink-0 cursor-pointer disabled:cursor-wait"
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Track */}
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke="var(--glass-border)"
          strokeWidth={2.5}
        />
        {/* Fill */}
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke={strokeColor}
          strokeWidth={2.5}
          strokeDasharray={circumference}
          strokeDashoffset={dashoffset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset 0.6s ease, stroke 0.4s ease' }}
        />
        {/* Pct label */}
        <text
          x={size / 2} y={size / 2 + 3.5}
          textAnchor="middle"
          fontSize={8}
          fontFamily="monospace"
          fill={strokeColor}
          style={{ transition: 'fill 0.4s ease' }}
        >
          {summarizing ? '…' : contextPct < 1 ? '' : Math.round(contextPct)}
        </text>
      </svg>
    </button>
  );
}
