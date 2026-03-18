interface DateSeparatorProps {
  timestamp: number;
}

function formatDate(ts: number): string {
  if (!ts) return '';
  const d = new Date(ts);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
}

export function DateSeparator({ timestamp }: DateSeparatorProps) {
  const label = formatDate(timestamp);
  if (!label) return null;
  return (
    <div className="sticky top-0 z-10 text-center text-xs text-[var(--text-muted)] font-mono py-3 -mx-6 px-6 bg-[var(--msg-user)]">
      {label}
    </div>
  );
}
