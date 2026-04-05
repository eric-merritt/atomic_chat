import { Icon } from '../atoms/Icon';

interface TowerAdProps {
  side: 'left' | 'right';
}

export function TowerAd({ side: _side }: TowerAdProps) {
  return (
    <div
      className="flex flex-col shrink-0
        w-40 h-[600px] max-h-[calc(100vh-3rem)]
        bg-[var(--glass-bg-solid)] border border-[var(--glass-border)]
        overflow-hidden shadow-lg"
    >
      {/* Ad slot — swap inner content for your ad network tag */}
      <div className="flex-1 flex flex-col items-center justify-center gap-4 p-4 text-center">
        <span className="text-[10px] uppercase tracking-widest text-[var(--text-muted)]">Ad</span>

        <div className="relative flex items-center justify-center">
          <Icon name="atom" size={120} className="text-[var(--accent)] opacity-20 [stroke-width:0.25]" />
          <p className="absolute text-xs font-semibold text-[var(--text-muted)] leading-snug px-1">
            Upgrade to Pro for unlimited tokens.
          </p>
        </div>

        <a
          href="/settings/billing"
          className="px-4 py-2 rounded-lg bg-[var(--accent)] text-[var(--bg-base)]
            text-xs font-semibold hover:opacity-90 transition-opacity"
        >
          Learn More
        </a>
      </div>
    </div>
  );
}
