import { useState, useRef, useEffect } from 'react';

export function EmojiPicker({ onEmojiSelect }: { onEmojiSelect: (emoji: string) => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Click outside to close
    const handleClickOutside = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleEmojiClick = (emoji: string) => {
    onEmojiSelect(emoji);
    setIsOpen(false);
  };

  const emojis = [
    '😀', '😃', '😄', '😁', '😆', '😅', '😂', '😊', '😇', '🙂', '😛',
    '👋', '🤚', '🖐', '✋', '🖖', '👌', '🤌', '🤏', '👍', '👎',
    '🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯',
    '🍎', '🍐', '🍊', '🍋', '🍌', '🍉', '🍇', '🍓', '🍒', '🍑',
    '🚗', '🚕', '🚙', '🚌', '🚎', '🏎', '🚓', '🚑', '🚒', '🚐',
    '⚽', '🏀', '🏈', '⚾', '🎾', '🏐', '🏉', '🎱', '🏓', '🏸',
    '⌚', '📱', '📷', '📸', '📹', '📞', '📟', '📠', '📡', '💻',
    '💎', '🔥', '✨', '⭐', '🌟', '💫', '💥', '💢', '💦', '💨',
    '🇺🇸', '🇬🇧', '🇫🇷', '🇩🇪', '🇯🇵', '🇨🇳', '🇮🇳', '🇧🇷', '🇦🇺', '🇨🇦'
  ];

  return (
    <>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="px-2 py-1 rounded-lg border border-[var(--glass-border)] text-[var(--text-secondary)] hover:bg-[var(--glass-highlight)] transition-all cursor-pointer flex items-center gap-1"
        title="Add emoji"
      >
        <span>😊</span>
      </button>

      {isOpen && (
        <div
          ref={pickerRef}
          className="absolute bottom-full left-0 mb-2 p-2 bg-[var(--glass-highlight)] border border-[var(--accent)] backdrop-blur-xl rounded-lg shadow-lg z-50 w-[250px] h-[250px] overflow-y-auto"
        >
          <div className="grid grid-cols-5 gap-1 text-xl">
            {emojis.map((emoji) => (
              <button
                key={emoji}
                onClick={() => handleEmojiClick(emoji)}
                className="hover:bg-[var(--glass-highlight)] p-1 rounded cursor-pointer transition-transform hover:scale-110"
              >
                {emoji}
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
