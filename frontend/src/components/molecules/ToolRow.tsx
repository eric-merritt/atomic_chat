import { Checkbox } from '../atoms/Checkbox';

interface ToolRowProps {
  name: string;
  description: string;
  selected: boolean;
  onToggle: () => void;
}

export function ToolRow({ name, description, selected, onToggle }: ToolRowProps) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 ml-5 hover:bg-[var(--glass-highlight)] rounded-lg cursor-pointer transition-colors"
      onClick={onToggle}
    >
      <Checkbox checked={selected} onChange={onToggle} onClick={(e) => e.stopPropagation()} />
      <span className="text-xs font-mono text-[var(--accent)] min-w-24">{name}</span>
      <span className="text-xs text-[var(--text-muted)] truncate">{description}</span>
    </div>
  );
}
