interface ConversationItemProps {
  title: string;
  date: string;
  folder: string | null;
  onClick: () => void;
  onDelete: () => void;
}

export function ConversationItem({ title, date, folder, onClick, onDelete }: ConversationItemProps) {
  return (
    <div
      onClick={onClick}
      className="flex items-center justify-between px-4 py-3 border-b border-[var(--glass-border)] hover:bg-[var(--msg-user)] cursor-pointer transition-colors"
    >
      <div className="flex-1 min-w-0">
        <div className="text-sm text-[var(--text)] font-medium truncate">{title}</div>
        <div className="text-xs text-[var(--text-muted)] mt-0.5">
          {new Date(date).toLocaleDateString()}
          {folder && <span className="ml-2 text-[var(--accent)]">#{folder}</span>}
        </div>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="text-xs text-[var(--text-muted)] hover:text-red-400 ml-2 cursor-pointer"
      >
        ✕
      </button>
    </div>
  );
}
