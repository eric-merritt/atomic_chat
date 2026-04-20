import { useState } from 'react'

export interface ApGalleryItem {
  title: string
  url: string
  preview_photo?: string
  preview_video?: string
  page_url?: string
}

interface Props {
  item: ApGalleryItem
  selected: boolean
  onToggle: () => void
}

export function ApGalleryCard({ item, selected, onToggle }: Props) {
  const [hovering, setHovering] = useState(false)
  const showVideo = hovering && !!item.preview_video

  return (
    <div
      className={[
        'relative rounded-lg overflow-hidden cursor-pointer group',
        'border transition-colors',
        selected
          ? 'border-[var(--accent)] ring-1 ring-[var(--accent)]'
          : 'border-[var(--glass-border)] hover:border-[var(--accent)]',
        'bg-[var(--glass-bg-solid)]',
      ].join(' ')}
      onClick={onToggle}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <div className="aspect-video bg-[var(--bg-base)] overflow-hidden">
        {showVideo ? (
          <video
            src={item.preview_video}
            className="w-full h-full object-cover"
            autoPlay
            muted
            loop
            playsInline
          />
        ) : item.preview_photo ? (
          <img
            src={item.preview_photo}
            alt={item.title}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-[var(--text-muted)] text-xs">
            no preview
          </div>
        )}
      </div>

      <input
        type="checkbox"
        checked={selected}
        onChange={() => {}}
        onClick={(e) => e.stopPropagation()}
        className="absolute top-1.5 left-1.5 w-4 h-4 accent-[var(--accent)] cursor-pointer"
      />

      <div className="p-2">
        <div className="text-xs text-[var(--text)] line-clamp-2 leading-tight" title={item.title}>
          {item.title}
        </div>
        {item.page_url && (
          <a
            href={item.page_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="mt-1 block text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] truncate"
            title={item.page_url}
          >
            {new URL(item.page_url).hostname}
          </a>
        )}
      </div>
    </div>
  )
}
