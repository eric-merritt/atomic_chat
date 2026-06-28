// Ring fills to 100% when context reaches TRIGGER_PCT. Clicking manually summarizes.
const TRIGGER_PCT = 75;

interface TrackProps { size: number; r: number; }
const Track = ({ size, r }: TrackProps) => (
  <circle
    cx={size / 2} cy={size / 2} r={r}
    fill="none"
    stroke="var(--glass-border)"
    strokeWidth={2.5}
  />
);

interface ArcProps { size: number; r: number; strokeColor: string; circumference: number; dashoffset: number; }
const Arc = ({ size, r, strokeColor, circumference, dashoffset }: ArcProps) => (
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
);

interface LabelProps { size: number; strokeColor: string; summarizing: boolean; displayPct: number; empty: boolean; }
const Label = ({ size, strokeColor, summarizing, displayPct, empty }: LabelProps) => (
  <text
    x={size / 2} y={size / 2 + 3.5}
    textAnchor="middle"
    fontSize={8}
    fontFamily="monospace"
    fill={strokeColor}
    style={{ transition: 'fill 0.4s ease' }}
  >
    {summarizing ? '…' : empty ? '' : displayPct}
  </text>
);

interface RingProps { size: number; r: number; strokeColor: string; circumference: number; dashoffset: number; summarizing: boolean; displayPct: number; empty: boolean; }
const Ring = ({ size, r, strokeColor, circumference, dashoffset, summarizing, displayPct, empty }: RingProps) => (
  <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
    <Track size={size} r={r} />
    <Arc size={size} r={r} strokeColor={strokeColor} circumference={circumference} dashoffset={dashoffset} />
    <Label size={size} strokeColor={strokeColor} summarizing={summarizing} displayPct={displayPct} empty={empty} />
  </svg>
);

import { type ReactNode } from 'react';

interface SummarizeButtonProps { onSummarize: () => void; summarizing: boolean; title: string; children: ReactNode; }
const SummarizeButton = ({ onSummarize, summarizing, title, children }: SummarizeButtonProps) => (
  <button
    id="inputContextRing"
    onClick={onSummarize}
    disabled={summarizing}
    title={title}
    className="shrink-0 cursor-pointer disabled:cursor-wait"
  >
    {children}
  </button>
);

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
  const title = contextPct < 1
    ? 'Context empty'
    : `Context: ${Math.round(fill * 100)}% — ${fill >= 1 ? 'click to summarize' : `auto-summarizes at ${TRIGGER_PCT}%`}`;

  return (
    <SummarizeButton onSummarize={onSummarize} summarizing={summarizing} title={title}>
      <Ring
        size={size} r={r}
        strokeColor={strokeColor}
        circumference={circumference}
        dashoffset={dashoffset}
        summarizing={summarizing}
        displayPct={Math.round(fill * 100)}
        empty={contextPct < 1}
      />
    </SummarizeButton>
  );
}
