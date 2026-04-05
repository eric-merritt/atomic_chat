interface AdBannerProps {
  onClose: () => void;
}

export function AdBanner({ onClose }: AdBannerProps) {
  return (
    <div className="shrink-0 w-full flex items-center justify-center px-4 py-2
      bg-[var(--glass-bg-solid)] border-b border-[var(--glass-border)]">
      {/* Ad slot — swap this content for your ad network tag */}
      <div className="flex-1 flex items-center gap-3 min-w-0">
        <span className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] shrink-0">
          Ad
        </span>
        <span className="text-sm text-[var(--text-secondary)] truncate">
          Unlock unlimited tokens — upgrade to Pro and never hit your daily limit.
        </span>
        <a
          href="/settings/billing"
          className="shrink-0 px-3 py-1 rounded-lg bg-[var(--accent)] text-[var(--bg-base)]
            text-xs font-semibold hover:opacity-90 transition-opacity"
        >
          Upgrade
        </a>
      </div>
      <button
        onClick={onClose}
        aria-label="Dismiss ad"
        className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)]
          text-lg leading-none cursor-pointer"
      >
        ×
      </button>
    </div>
  );
}
