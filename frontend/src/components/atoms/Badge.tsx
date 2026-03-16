import type { ReactNode } from 'react';

export function Badge({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-[var(--accent-glow)] text-[var(--accent)] border border-[var(--glass-border)] ${className}`}>
      {children}
    </span>
  );
}
