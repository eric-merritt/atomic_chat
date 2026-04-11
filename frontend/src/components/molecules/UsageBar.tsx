import { useState, useEffect } from 'react';
interface UsageStatus {
  percent: number;
}

const THRESHOLDS = [75, 80, 85, 90, 95, 99];

function activeThreshold(pct: number): number | null {
  for (let i = THRESHOLDS.length - 1; i >= 0; i--) {
    if (pct >= THRESHOLDS[i]) return THRESHOLDS[i];
  }
  return null;
}

function storageKey(): string {
  return `usage_dismissed_${new Date().toISOString().slice(0, 10)}`;
}

function loadDismissed(): Set<number> {
  try {
    const raw = localStorage.getItem(storageKey());
    if (raw) return new Set(JSON.parse(raw));
  } catch { /* ignore */ }
  return new Set();
}

function saveDismissed(set: Set<number>) {
  try {
    localStorage.setItem(storageKey(), JSON.stringify([...set]));
  } catch { /* ignore */ }
}

interface UsageBarProps {
  usage: UsageStatus;
}

export function UsageBar({ usage }: UsageBarProps) {
  const [dismissed, setDismissed] = useState<Set<number>>(loadDismissed);

  const pct = usage.percent;
  const threshold = activeThreshold(pct);
  const visible = threshold !== null && !dismissed.has(threshold);

  // Re-check dismissed state from storage when usage updates (e.g. new day)
  useEffect(() => {
    setDismissed(loadDismissed());
  }, [pct]);

  if (!visible) return null;

  const isNear = pct >= 90;

  function dismiss() {
    if (threshold === null) return;
    const next = new Set(dismissed).add(threshold);
    saveDismissed(next);
    setDismissed(next);
  }

  return (
    <div className="w-full px-1 pb-1">
      <div className="flex items-center justify-between text-[10px] mb-0.5">
        <span className={isNear ? 'text-red-400 font-semibold' : 'text-[var(--text-muted)]'}>
          {pct >= 100
            ? 'Daily limit reached'
            : `${pct}% Daily Limit Reached`}
        </span>
        <div className="flex items-center gap-2">
          <a
            href="/settings/billing"
            className="text-[var(--accent)] hover:underline font-semibold"
          >
            Boost Your Use Here
          </a>
          <button
            onClick={dismiss}
            aria-label="Dismiss"
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] leading-none cursor-pointer"
          >
            ×
          </button>
        </div>
      </div>
      <div className="h-1 rounded-full bg-[var(--glass-bg-solid)] overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            isNear ? 'bg-red-500' : 'bg-[var(--accent)]'
          }`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
}
