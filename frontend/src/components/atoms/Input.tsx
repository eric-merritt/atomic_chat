import type { InputHTMLAttributes } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

export function Input({ className = '', ...props }: InputProps) {
  return (
    <input
      type="text"
      className={`flex-[3] min-w-0 bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2 text-sm font-light font-mono outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_var(--accent-glow)] transition-all placeholder:text-[var(--text-muted)] ${className}`}
      {...props}
    />
  );
}
