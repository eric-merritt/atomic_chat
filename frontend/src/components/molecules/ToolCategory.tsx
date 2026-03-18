import { Checkbox } from '../atoms/Checkbox';
import { Icon } from '../atoms/Icon';

interface ToolCategoryProps {
  name: string;
  count: number;
  selectedCount: number;
  allSelected: boolean;
  someSelected: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleAll: () => void;
}

export function ToolCategory({
  name, count, selectedCount, allSelected, someSelected,
  expanded, onToggleExpand, onToggleAll,
}: ToolCategoryProps) {
  return (
    <div
      className={`flex items-center gap-2 px-3 py-2.5 cursor-pointer transition-colors ${expanded ? 'bg-[var(--msg-user)]' : ''}`}
      onClick={onToggleExpand}
    >
      <Icon name="chevron" size={14} className={`text-[var(--text-muted)] transition-transform ${expanded ? 'rotate-90' : ''}`} />
      <span className="flex-1 text-sm text-[var(--text)] font-medium">{name}</span>
      <span className="text-xs text-[var(--text-muted)] font-mono mr-1">{selectedCount}/{count}</span>
      <Checkbox
        checked={allSelected}
        indeterminate={someSelected && !allSelected}
        onChange={(e) => { e.stopPropagation(); onToggleAll(); }}
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}
