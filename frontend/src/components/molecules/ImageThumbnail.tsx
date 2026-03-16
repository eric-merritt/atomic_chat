interface ImageThumbnailProps {
  src: string;
  filename: string;
  sizeKb: number;
  onClick: () => void;
}

export function ImageThumbnail({ src, filename, sizeKb, onClick }: ImageThumbnailProps) {
  return (
    <div className="self-start cursor-pointer" onClick={onClick}>
      <img
        src={src}
        alt={filename}
        className="max-w-[280px] max-h-[200px] rounded-xl border border-[var(--glass-border)] hover:brightness-115 hover:scale-[1.01] transition-all"
      />
      <div className="text-xs text-[var(--text-muted)] font-mono mt-1">
        {filename} ({sizeKb} KB)
      </div>
    </div>
  );
}
