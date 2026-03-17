import { useState, useRef, useCallback } from 'react';
import { Badge } from '../atoms/Badge';
import { Icon } from '../atoms/Icon';

interface ToolChipProps {
  selected: string[];
  onRemove: (name: string) => void;
}

export function ToolChip({ selected, onRemove }: ToolChipProps) {
  const [showPopup, setShowPopup] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancelClose = useCallback(() => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const open = useCallback(() => {
    cancelClose();
    setShowPopup(true);
  }, [cancelClose]);

  const scheduleClose = useCallback(() => {
    cancelClose();
    closeTimer.current = setTimeout(() => setShowPopup(false), 300);
  }, [cancelClose]);

  if (selected.length === 0) return null;

  return (
    <div
      className="relative"
      onMouseEnter={open}
      onMouseLeave={scheduleClose}
    >
      <Badge className="tracking-[0.15em] px-8">
        <Icon name="wrench" size={14} />
        {selected.length} Tools Selected
      </Badge>
      {showPopup && (
        /* pb-2 on wrapper creates an invisible bridge over the gap so the
           mouse stays inside the hover zone while moving from badge → list */
        <div
          className="absolute bottom-full left-0 pb-2 z-50"
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
        >
          <div className="bg-[var(--bg-base)] bg-opacity-95 border border-[var(--glass-border)] rounded-lg p-2 min-w-48 backdrop-blur-xl">
            {selected.map((name) => (
              <div key={name} className="flex items-center justify-between gap-2 py-1 px-2 text-sm text-[var(--text)]">
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
        </div>
      )}
    </div>
  );
}
