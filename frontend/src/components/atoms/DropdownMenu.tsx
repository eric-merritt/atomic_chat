import { useEffect, useRef } from 'react';

interface MenuItem {
  label: string;
  onClick: () => void;
}

interface DropdownMenuProps {
  items: MenuItem[];
  open: boolean;
  onClose: () => void;
  className?: string;
}

export function DropdownMenu({ items, open, onClose, className = '' }: DropdownMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={ref}
      className={`absolute z-50 bg-[var(--glass-bg-solid)] border border-[var(--accent)] rounded-lg shadow-lg overflow-hidden ${className}`}
    >
      {items.map((item) => (
        <button
          key={item.label}
          onClick={() => { item.onClick(); onClose(); }}
          className="w-full text-left px-4 py-2 text-sm text-[var(--text)] hover:bg-[var(--msg-user)] transition-colors cursor-pointer"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
