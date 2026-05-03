import { useState, type ReactNode } from 'react'
import { ApGalleryCard, type ApGalleryItem } from '../molecules/ApGalleryCard'
import { useChat } from '../../hooks/useChat'
import { useModels } from '../../hooks/useModels'

export interface ApGalleryPayload {
  items: ApGalleryItem[]
  caption?: string
}

interface Props {
  payload: ApGalleryPayload
  columns: 3 | 6
  leftRail?: ReactNode
  initialSelection?: Set<number>
  onSubmitSent?: () => void
}

const colClass: Record<3 | 6, string> = {
  3: 'grid-cols-3',
  6: 'grid-cols-6',
}

export function ApGallery({ payload, columns, leftRail, initialSelection, onSubmitSent }: Props) {
  const { sendMessage } = useChat()
  const { saveDir } = useModels()
  const [selected, setSelected] = useState<Set<number>>(initialSelection ?? new Set())

  const toggle = (i: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  const selectAll = () => {
    setSelected(new Set(payload.items.map((_, i) => i)))
  }

  const clear = () => setSelected(new Set())

  const submit = () => {
    if (selected.size === 0) return
    const chosen = [...selected]
      .sort((a, b) => a - b)
      .map((i) => payload.items[i])
    const lines = chosen.map((it) => `- ${it.title}: ${it.url}`).join('\n')
    sendMessage(
      `For each of the following links, call www_find_dl to extract the direct download URL, ` +
      `then download it to ${saveDir}:\n${lines}`
    )
    clear()
    onSubmitSent?.()
  }

  return (
    <div className="flex w-full rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-solid)] overflow-hidden">
      {leftRail && (
        <div className="flex flex-col items-center justify-start gap-2 py-2 px-1 border-r border-[var(--glass-border)] bg-[var(--bg-base)]">
          {leftRail}
        </div>
      )}

      <div className="flex-1 min-w-0">
        {(payload.caption || payload.items.length > 0) && (
          <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--glass-border)]">
            <span className="text-xs text-[var(--text-muted)]">
              {payload.caption || `${payload.items.length} items`}
            </span>
            <div className="flex items-center gap-2 text-[10px]">
              <button
                onClick={selectAll}
                className="text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer"
              >
                All
              </button>
              <button
                onClick={clear}
                className="text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer"
              >
                None
              </button>
              <span className="text-[var(--text-muted)]">·</span>
              <span className="text-[var(--accent)]">{selected.size} selected</span>
            </div>
          </div>
        )}

        <div className={`grid gap-2 p-2 ${colClass[columns]}`}>
          {payload.items.map((item, i) => (
            <ApGalleryCard
              key={`${i}-${item.url}`}
              item={item}
              selected={selected.has(i)}
              onToggle={() => toggle(i)}
            />
          ))}
        </div>

        <div className="flex justify-end px-3 py-2 border-t border-[var(--glass-border)]">
          <button
            onClick={submit}
            disabled={selected.size === 0}
            className={[
              'px-3 py-1 rounded text-xs transition-colors',
              selected.size > 0
                ? 'bg-[var(--accent)] text-[var(--bg-base)] hover:brightness-110 cursor-pointer'
                : 'bg-[var(--glass-bg-solid)] text-[var(--text-muted)] cursor-not-allowed border border-[var(--glass-border)]',
            ].join(' ')}
          >
            Send selection
          </button>
        </div>
      </div>
    </div>
  )
}
