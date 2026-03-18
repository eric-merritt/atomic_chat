import { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Checkbox } from '../atoms/Checkbox';

interface ToolRowProps {
  name: string;
  description: string;
  selected: boolean;
  onToggle: () => void;
}

export function ToolRow({ name, description, selected, onToggle }: ToolRowProps) {
  const [hovered, setHovered] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const rect = hovered && ref.current ? ref.current.getBoundingClientRect() : null;

  return (
    <div
      ref={ref}
      className="relative flex items-center gap-1.5 px-2 py-1 hover:bg-[var(--glass-highlight)] cursor-pointer transition-colors"
      onClick={onToggle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <Checkbox checked={selected} onChange={onToggle} onClick={(e) => e.stopPropagation()} />
      <span className="text-xs font-mono text-[var(--accent)] truncate">{name}</span>
      {hovered && description && rect && createPortal(
        <div
          className="fixed px-2 py-1 rounded text-xs whitespace-nowrap bg-[var(--msg-user)] border border-[var(--accent)] text-[var(--text)] shadow-lg z-[9999] pointer-events-none animate-[msgIn_0.1s_ease-out]"
          style={{
            top: rect.top + rect.height / 2,
            left: rect.right + 40,
            transform: 'translateY(-50%)',
          }}
        >
          {description}
        </div>,
        document.getElementById('tooltip-root')!
      )}
    </div>
  );
}
