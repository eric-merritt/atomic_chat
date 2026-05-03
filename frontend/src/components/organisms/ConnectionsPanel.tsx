import { useState } from 'react';
import { useMcpServers } from '../../hooks/useMcpServers';
import type { McpServer } from '../../api/mcp';

const TIER_LABELS: Record<string, string> = { free: 'Free', freemium: 'Freemium', paid: 'Paid' };

const TIER_COLORS: Record<string, string> = {
  free: 'text-green-400',
  freemium: 'text-yellow-400',
  paid: 'text-red-400',
};

const TierBadge = ({ tier }: { tier: string }) => (
  <span className={ `text-xs font-medium ${ TIER_COLORS[tier] ?? 'text-[var(--text-muted)]' }` }>
    { TIER_LABELS[tier] ?? tier }
  </span>
);

const PartnerBadge = () => (
  <span className="text-xs text-[var(--accent)] font-medium">Partner</span>
);

const ServerRow = ({ server }: { server: McpServer }) => (
  <a
    href={ server.url }
    target="_blank"
    rel="noopener noreferrer"
    className="flex items-start gap-3 p-3 rounded-lg hover:bg-[var(--bg-hover)] transition-colors"
  >
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium text-[var(--text)] truncate">{ server.name }</span>
        <TierBadge tier={ server.tier } />
        { server.partnership_potential && <PartnerBadge /> }
      </div>
      <p className="text-xs text-[var(--text-muted)] mt-0.5 line-clamp-2">{ server.description }</p>
    </div>
    <span className="text-xs text-[var(--text-muted)] shrink-0 pt-0.5">{ server.category }</span>
  </a>
);

const FilterBar = ({
  categories,
  activeCategory,
  activeTier,
  onCategory,
  onTier,
}: {
  categories: string[];
  activeCategory: string;
  activeTier: string;
  onCategory: (c: string) => void;
  onTier: (t: string) => void;
}) => (
  <div className="flex flex-wrap gap-2 mb-3">
    <select
      value={ activeTier }
      onChange={ e => onTier(e.target.value) }
      className="text-xs bg-[var(--bg-input)] text-[var(--text)] border border-[var(--border)] rounded px-2 py-1"
    >
      <option value="">All tiers</option>
      { ['free', 'freemium', 'paid'].map(t => (
        <option key={ t } value={ t }>{ TIER_LABELS[t] }</option>
      )) }
    </select>
    <select
      value={ activeCategory }
      onChange={ e => onCategory(e.target.value) }
      className="text-xs bg-[var(--bg-input)] text-[var(--text)] border border-[var(--border)] rounded px-2 py-1"
    >
      <option value="">All categories</option>
      { categories.map(c => (
        <option key={ c } value={ c }>{ c }</option>
      )) }
    </select>
  </div>
);

export function ConnectionsPanel() {
  const [activeTier, setActiveTier] = useState('');
  const [activeCategory, setActiveCategory] = useState('');

  const filters = {
    ...( activeTier ? { tier: activeTier as 'free' | 'freemium' | 'paid' } : {} ),
    ...( activeCategory ? { category: activeCategory } : {} ),
  };

  const { servers, categories, asOf, loading, error } = useMcpServers(filters);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-[var(--text)]">MCP Servers</h2>
        { asOf && <span className="text-xs text-[var(--text-muted)]">as of { asOf }</span> }
      </div>

      <FilterBar
        categories={ categories }
        activeCategory={ activeCategory }
        activeTier={ activeTier }
        onCategory={ setActiveCategory }
        onTier={ setActiveTier }
      />

      { loading && (
        <p className="text-sm text-[var(--text-muted)] text-center py-8">Loading…</p>
      ) }

      { error && (
        <p className="text-sm text-red-400 text-center py-8">{ error }</p>
      ) }

      { !loading && !error && (
        <div className="flex-1 overflow-y-auto space-y-1">
          { servers.map(server => <ServerRow key={ server.id } server={ server } /> ) }
          { servers.length === 0 && (
            <p className="text-sm text-[var(--text-muted)] text-center py-8">No servers match the filter.</p>
          ) }
        </div>
      ) }
    </div>
  );
}
