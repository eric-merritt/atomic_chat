interface TimestampProps {
  timestamp: number;
  align: 'left' | 'right';
}

function formatTime(ts: number): string {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export function Timestamp({ timestamp, align }: TimestampProps) {
  const time = formatTime(timestamp);
  if (!time) return null;
  return (
    <span className={`text-[10px] text-[var(--text-muted)] font-mono mt-0.5 mx-2 ${align === 'right' ? 'self-end' : 'self-start'}`}>
      {time}
    </span>
  );
}
