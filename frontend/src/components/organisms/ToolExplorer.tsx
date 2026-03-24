import { useState, useMemo } from 'react';
import { useWorkspace } from '../../hooks/useWorkspace';
import { GroupCard } from '../molecules/GroupCard';

export function ToolExplorer() {
  const { groups, activeGroups, openGroup, closeGroup } = useWorkspace();
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return groups;
    const q = search.toLowerCase();
    return groups.filter(
      (g) =>
        g.name.toLowerCase().includes(q) ||
        g.tooltip.toLowerCase().includes(q) ||
        g.tools.some((t) => t.name.toLowerCase().includes(q)),
    );
  }, [groups, search]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Search */}
      <div className="px-2 pt-2 pb-1 shrink-0">
        <div className="relative">
          <input
            type="text"
            placeholder="Search tools..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full text-xs font-mono px-2 py-1.5 rounded-lg bg-[var(--glass-highlight)] border border-[var(--glass-border)] text-[var(--text)] placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent)] transition-colors"
          />
          {search && (
            <button
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer text-sm"
              onClick={() => setSearch('')}
              title="Clear search"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      {/* Group cards */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-20">
            <span className="text-xs text-[var(--text-muted)]">No matching tools</span>
          </div>
        ) : (
          <div className="flex flex-col gap-2 pt-1">
            {filtered.map((g) => (
              <GroupCard
                key={g.name}
                name={g.name}
                tooltip={g.tooltip}
                tools={g.tools}
                active={activeGroups.includes(g.name)}
                onOpen={openGroup}
                onClose={closeGroup}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
