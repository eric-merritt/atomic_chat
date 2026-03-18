import { type MouseEventHandler } from 'react';

interface CheckboxProps {
  checked?: boolean;
  indeterminate?: boolean;
  onChange?: (e: { stopPropagation: () => void }) => void;
  onClick?: MouseEventHandler;
  className?: string;
}

export function Checkbox({ checked = false, indeterminate = false, onChange, onClick, className = '' }: CheckboxProps) {
  return (
    <div
      className={`w-4 h-4 rounded border border-[var(--accent)] flex items-center justify-center cursor-pointer shrink-0 transition-colors ${className}`}
      style={{
        background: checked || indeterminate
          ? 'radial-gradient(circle at center, color-mix(in srgb, var(--accent) 70%, transparent) 0%, color-mix(in srgb, var(--accent) 30%, transparent) 60%, transparent 100%)'
          : 'transparent',
      }}
      onClick={(e) => {
        onClick?.(e);
        onChange?.(e);
      }}
    >
    </div>
  );
}
