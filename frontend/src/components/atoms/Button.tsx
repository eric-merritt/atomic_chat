import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonVariant = 'primary' | 'ghost' | 'danger';

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] disabled:opacity-30',
  ghost: 'bg-transparent border border-[var(--glass-border)] text-[var(--text-secondary)] hover:bg-[var(--glass-highlight)]',
  danger: 'bg-[var(--danger)] text-white hover:brightness-110',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant: ButtonVariant;
  children: ReactNode;
}

export function Button({ variant, children, className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${variantClasses[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
