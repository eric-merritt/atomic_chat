import { ConversationTitle } from './ConversationTitle';
import { NewConversationButton } from './NewConversationButton';

function formatDate(ts: number): string {
  if (!ts) return 'Today';
  const d = new Date(ts);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
}

interface ChatTopBarProps {
  visibleDate: number;
}

export function ChatTopBar({ visibleDate }: ChatTopBarProps) {
  return (
    <div className="sticky top-0 z-30 shrink-0 relative flex items-center justify-center bg-[var(--glass-bg-solid)] border-b border-[var(--glass-border)] py-2">
      <div className="absolute left-0 top-0 bottom-0 flex items-center px-3 border-r border-[var(--glass-border)]">
        <ConversationTitle />
      </div>
      <span className="text-xs text-[var(--text-muted)] font-mono">
        {formatDate(visibleDate)}
      </span>
      <div className="absolute right-0 top-0 bottom-0 flex items-center px-2 border-l border-[var(--glass-border)]">
        <NewConversationButton />
      </div>
    </div>
  );
}
