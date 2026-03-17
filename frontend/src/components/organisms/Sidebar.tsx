import { useState } from 'react';
import { CategoryHeader } from '../molecules/CategoryHeader';
import { ToolRow } from '../molecules/ToolRow';
import { Icon } from '../atoms/Icon';
import { useTools } from '../../hooks/useTools';

interface SidebarProps {
  expanded: boolean;
  onToggle: () => void;
}

export function Sidebar({ expanded, onToggle }: SidebarProps) {
  const { categories, toggleTool, toggleCategory } = useTools();
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());

  const toggleCatExpand = (name: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  return (
    <div className={`flex flex-col backdrop-blur-xl border border-[var(--accent)] rounded-[14px] m-2 overflow-hidden shadow-[0_4px_24px_rgba(0,0,0,0.15)] transition-colors ${expanded ? 'bg-[var(--glass-bg)]' : 'bg-transparent hover:bg-[var(--glass-bg)]'}`}>
      <div
        className={`group/toggle flex items-center justify-center w-full p-3 cursor-pointer hover:bg-[var(--glass-highlight)] transition-colors ${expanded ? '' : 'flex-1'}`}
        onClick={onToggle}
        title="Toggle tools"
      >
        <Icon name="chevron" size={18} className={`text-[var(--accent)] group-hover/toggle:text-[var(--glass-border)] transition-all ${expanded ? 'rotate-180' : ''}`} />
      </div>

      {expanded && (
        <div className="flex-1 overflow-y-auto px-2 pb-2">
          <div className="text-sm font-semibold text-[var(--text)] px-3 py-2">Tools</div>
          {categories.map((cat) => (
            <div key={cat.name}>
              <CategoryHeader
                name={cat.name}
                count={cat.count}
                selectedCount={cat.selectedCount}
                allSelected={cat.allSelected}
                someSelected={cat.someSelected}
                expanded={expandedCats.has(cat.name)}
                onToggleExpand={() => toggleCatExpand(cat.name)}
                onToggleAll={() => toggleCategory(cat.name)}
              />
              {expandedCats.has(cat.name) && cat.tools.map((tool) => (
                <ToolRow
                  key={tool.name}
                  name={tool.name}
                  description={tool.description}
                  selected={tool.selected}
                  onToggle={() => toggleTool(tool.name)}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
