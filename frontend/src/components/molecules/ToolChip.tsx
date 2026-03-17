import { useState } from 'react';
import { Badge } from '../atoms/Badge';
import { Icon } from '../atoms/Icon';

interface ToolChipProps {
  selected: string[];
  onRemove: (name: string) => void;
}

export function ToolChip({ selected, onRemove }: ToolChipProps) {
  const [showPopup, setShowPopup] = useState(false);

  if (selected.length === 0) return null;

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowPopup(true)}
      onMouseLeave={() => setShowPopup(false)}
    >
      <Badge>
        <Icon name="wrench" size={14} />
        {selected.length} tools
      </Badge>
      {showPopup && (
        <div className="absolute bottom-full left-0 mb-2 bg-[var(--glass-bg-solid)] border border-[var(--glass-border)] rounded-lg p-2 min-w-48 backdrop-blur-xl z-50">
          {selected.map((name) => (
            <div key={name} className="flex items-center justify-between gap-2 py-1 px-2 text-xs text-[var(--text)]">
              <span className="font-mono">{name}</span>
              <span
                className="cursor-pointer text-[var(--danger)] hover:brightness-125"
                onClick={() => onRemove(name)}
              >
                <Icon name="close" size={12} />
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
