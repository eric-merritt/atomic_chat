import { Dot } from '../atoms/Dot';

interface ThinkingIndicatorProps {
  label: string;
  elapsed: number;
  preview: string;
}

export function ThinkingIndicator({ label, elapsed, preview }: ThinkingIndicatorProps) {
  return (
    <div className="self-start max-w-[75%] px-4 py-3 rounded-xl bg-[var(--msg-assistant)] border border-[var(--glass-border)]">
      <div className="flex items-center gap-2 mb-1">
        <div className="flex gap-1">
          <Dot delay="0s" />
          <Dot delay="0.2s" />
          <Dot delay="0.4s" />
        </div>
        <span className="text-xs text-[var(--text-secondary)]">{label}</span>
        <span className="text-xs text-[var(--text-muted)] font-mono tabular-nums ml-auto">
          {elapsed}s
        </span>
      </div>
      {preview && (
        <div className="text-xs text-[var(--text-muted)] font-mono truncate max-w-full">
          {preview}
        </div>
      )}
    </div>
  );
}
