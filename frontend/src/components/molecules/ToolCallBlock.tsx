// frontend/src/components/molecules/ToolCallBlock.tsx
import { useState } from 'react'
import { HierarchyRenderer } from '../atoms/HierarchyRenderer'
import { getAdapter } from '../../lib/toolAdapters'

export interface ToolCallPair {
  tool: string
  params: unknown        // parsed from tool_call input JSON
  result: unknown | null // null while streaming
  status: 'streaming' | 'done'
}

interface Props {
  pair: ToolCallPair
  onFileClick: (path: string) => void
  bubbleHeightPx: number
}

export function ToolCallBlock({ pair, onFileClick, bubbleHeightPx }: Props) {
  const [expanded, setExpanded] = useState(false)
  const adapter = getAdapter(pair.tool)

  const digest = pair.result && adapter
    ? adapter.summarize(pair.params, pair.result) : null

  const nodes = pair.result && adapter
    ? adapter.toHierarchy(pair.params, pair.result) : []

  const expandedHeight = Math.floor(bubbleHeightPx * 0.6)

  if (pair.status === 'streaming') {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono text-[var(--text-muted)]">
        <span className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse inline-block" />
        <span>{pair.tool}</span>
        <span className="opacity-50">running…</span>
      </div>
    )
  }

  return (
    <div
      className="rounded-lg overflow-hidden transition-all duration-300 my-1"
      style={{
        border: '1px solid color-mix(in srgb, var(--accent) 25%, transparent)',
        background: 'color-mix(in srgb, var(--msg-assistant) 50%, transparent)',
      }}
    >
      <button
        onClick={() => nodes.length > 0 && setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-xs font-mono text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors cursor-pointer"
      >
        <span className="text-[var(--accent)]">✓</span>
        <span className="font-medium text-[var(--accent)] opacity-70">{pair.tool}</span>
        {digest && (
          <>
            <span className="opacity-40">·</span>
            <span className="truncate">{digest}</span>
          </>
        )}
        {nodes.length > 0 && (
          <span className="ml-auto text-[10px] shrink-0">{expanded ? '▲' : '▼'}</span>
        )}
      </button>

      {expanded && nodes.length > 0 && (
        <div
          className="overflow-y-auto px-3 pb-2 border-t"
          style={{
            maxHeight: `${expandedHeight}px`,
            borderColor: 'color-mix(in srgb, var(--accent) 15%, transparent)',
          }}
        >
          <HierarchyRenderer nodes={nodes} onFileClick={onFileClick} />
        </div>
      )}
    </div>
  )
}
