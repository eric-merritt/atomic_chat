import { useEffect } from 'react';

interface LightboxProps {
  src: string;
  caption: string;
  onClose: () => void;
}

export function Lightbox({ src, caption, onClose }: LightboxProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/80 backdrop-blur-sm cursor-pointer"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <img
        src={src}
        alt={caption}
        className="max-w-[90vw] max-h-[85vh] rounded-xl shadow-2xl"
      />
      {caption && (
        <div className="mt-3 text-sm text-white/70 font-mono">{caption}</div>
      )}
    </div>
  );
}
