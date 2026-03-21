import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

interface MenuItem {
  label: string;
  onClick: () => void;
}

interface DropdownMenuProps {
  items: MenuItem[];
  open: boolean;
  onClose: () => void;
  anchorRef?: React.RefObject<HTMLElement | null>;
  className?: string;
}

export function DropdownMenu({ items, open, onClose, anchorRef, className = '' }: DropdownMenuProps) {
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

  const rect = anchorRef?.current?.getBoundingClientRect();
  const style: React.CSSProperties = rect
    ? { position: 'fixed', top: rect.bottom + 4, right: window.innerWidth - rect.right }
    : {};

  const menu = (
    <div
      ref={ref}
      style={style}
      className={`${rect ? 'fixed' : 'absolute'} z-[9999] bg-[var(--glass-bg-solid)] backdrop-blur-lg border border-[var(--accent)] rounded-lg shadow-lg overflow-hidden ${className}`}
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

  return rect ? createPortal(menu, document.body) : menu;
}
