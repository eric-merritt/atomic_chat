import { useState } from 'react';
import { ToolCategory } from '../molecules/ToolCategory';
import { ToolRow } from '../molecules/ToolRow';
import { Icon } from '../atoms/Icon';
import { useTools } from '../../hooks/useTools';
import { getSubcategory } from '../../api/tools';
import type { Tool } from '../../atoms/tool';

interface SidebarProps {
  expanded: boolean;
  onToggle: () => void;
}

/** Group tools by their subcategory, preserving order of first appearance. */
function groupBySub(tools: Tool[]): Map<string, Tool[]> {
  const groups = new Map<string, Tool[]>();
  for (const t of tools) {
    const sub = getSubcategory(t.name) ?? 'other';
    if (!groups.has(sub)) groups.set(sub, []);
    groups.get(sub)!.push(t);
  }
  return groups;
}

const SUBCATEGORIZED = new Set(['Marketplace']);

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
    <div
      className={`flex border border-[var(--accent)] rounded-[14px] m-2 overflow-hidden shadow-[0_4px_24px_rgba(0,0,0,0.15)] transition-colors ${expanded ? 'backdrop-blur-md'
        : 'bg-transparent hover:backdrop-blur-md cursor-pointer'}`}
    >
      {/* Main content column */}
      <div className="flex-1 flex flex-col overflow-hidden" onClick={expanded ? undefined : onToggle}>
        <div className="text-sm font-semibold text-[var(--text)] py-2 pl-4 text-center underline">
            Tools
        </div>

        {expanded && (
          <div className="flex-1 overflow-y-auto px-2 pb-2 pr-4">
            <div className="flex flex-col">
              {categories.map((cat) => {
                const hasSubs = SUBCATEGORIZED.has(cat.name);
                const subGroups = hasSubs ? [...groupBySub(cat.tools)] : [];

                return (
                  <div
                    key={cat.name}
                    className={`transition-all ${
                      expandedCats.has(cat.name)
                        ? 'border-x-0 border-b border-[var(--glass-border)] -mx-2'
                        : 'bg-[var(--msg-user)] border border-[var(--glass-border)] hover:border-[var(--accent)] rounded-lg mx-2 my-2'
                    }`}
                  >
                    <ToolCategory
                      name={cat.name}
                      count={cat.count}
                      selectedCount={cat.selectedCount}
                      allSelected={cat.allSelected}
                      someSelected={cat.someSelected}
                      expanded={expandedCats.has(cat.name)}
                      onToggleExpand={() => toggleCatExpand(cat.name)}
                      onToggleAll={() => toggleCategory(cat.name)}
                    />
                    {expandedCats.has(cat.name) && (
                      <div className="border-t border-[var(--glass-border)]">
                        {hasSubs ? (
                          <div className="flex flex-col">
                            {subGroups.map(([sub, tools], i) => (
                              <div key={sub} className={i > 0 ? 'border-t border-[var(--glass-border)]' : ''}>
                                <div className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] px-3 py-1.5 font-semibold bg-[var(--msg-assistant)]">{sub}</div>
                                <div className="flex flex-col">
                                  {tools.map((tool) => (
                                    <ToolRow
                                      key={tool.name}
                                      name={tool.name}
                                      description={tool.description}
                                      selected={tool.selected}
                                      onToggle={() => toggleTool(tool.name)}
                                    />
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="flex flex-col">
                            {cat.tools.map((tool) => (
                              <ToolRow
                                key={tool.name}
                                name={tool.name}
                                description={tool.description}
                                selected={tool.selected}
                                onToggle={() => toggleTool(tool.name)}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Chevron column — always visible, vertically centered */}
      <div
        className={`flex items-center justify-center cursor-pointer transition-colors ${expanded ? 'backdrop-blur-md' : ''}`}
        onClick={onToggle}
        title="Toggle tools"
      >
        <Icon name="chevron" size={18} className={`text-[var(--accent)] transition-all ${expanded ? 'rotate-180' : ''}`} />
      </div>
    </div>
  );
}
