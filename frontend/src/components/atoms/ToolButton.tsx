interface ToolButtonProps {
  name: string;
  selected: boolean;
  onClick: () => void;
}

export function ToolButton({ name, selected, onClick }: ToolButtonProps) {
  return (
    <button
      className={`px-2 py-1 text-xs font-mono rounded-md border cursor-pointer transition-colors ${
        selected
          ? 'border-[var(--accent)] bg-[var(--accent)] text-[var(--bg-base)]'
          : 'border-[var(--glass-border)] text-[var(--accent)] hover:border-[var(--accent)] bg-transparent'
      }`}
      onClick={onClick}
    >
      {name}
    </button>
  );
}
