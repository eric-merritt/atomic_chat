import type { ReactNode } from 'react';

export function StatusText({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span className={`text-xs text-[var(--text-muted)] font-light ${className}`}>
      {children}
    </span>
  );
}
