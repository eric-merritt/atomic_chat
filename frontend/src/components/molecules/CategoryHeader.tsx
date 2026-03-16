import { Checkbox } from '../atoms/Checkbox';
import { Icon } from '../atoms/Icon';

interface CategoryHeaderProps {
  name: string;
  count: number;
  selectedCount: number;
  allSelected: boolean;
  someSelected: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleAll: () => void;
}

export function CategoryHeader({
  name, count, selectedCount, allSelected, someSelected,
  expanded, onToggleExpand, onToggleAll,
}: CategoryHeaderProps) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-[var(--glass-highlight)] rounded-lg transition-colors"
      onClick={onToggleExpand}
    >
      <Icon
        name="chevron"
        size={14}
        className={`transition-transform ${expanded ? 'rotate-90' : ''}`}
      />
      <Checkbox
        checked={allSelected}
        indeterminate={someSelected && !allSelected}
        onChange={(e) => { e.stopPropagation(); onToggleAll(); }}
        onClick={(e) => e.stopPropagation()}
      />
      <span className="text-sm text-[var(--text)] font-medium flex-1">{name}</span>
      <span className="text-xs text-[var(--text-muted)] font-mono">{selectedCount}/{count}</span>
    </div>
  );
}
