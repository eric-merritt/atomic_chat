import { useState } from 'react'
import { Icon } from '../atoms/Icon'
import { HierarchyRenderer } from '../atoms/HierarchyRenderer'
import { getAdapter } from '../../lib/toolAdapters'
import type { ToolCallPair } from '../../atoms/message'

interface Props {
  pair: ToolCallPair
  onFileClick: (path: string) => void
  bubbleHeightPx: number
}

// Open-end wrench jaw (right cap). Height must match SHAFT_H.
const SHAFT_H = 36

function WrenchJaw() {
  const h = SHAFT_H
  const w = 14
  // Two prongs with a gap in the middle; left edge open (connects to shaft).
  const prong = Math.round(h * 0.38)  // prong thickness
  const gap   = h - prong * 2         // gap between prongs
  const r     = 3                     // corner radius
  const inner = 5                     // inner ledge depth

  const topProngPath = [
    `M 0,0`,
    `L ${w - r},0 Q ${w},0 ${w},${r}`,
    `L ${w},${prong - r} Q ${w},${prong} ${w - r},${prong}`,
    `L ${inner},${prong}`,
  ].join(' ')

  const botProngPath = [
    `M ${inner},${prong + gap}`,
    `L ${w - r},${prong + gap} Q ${w},${prong + gap} ${w},${prong + gap + r}`,
    `L ${w},${h - r} Q ${w},${h} ${w - r},${h}`,
    `L 0,${h}`,
  ].join(' ')

  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      fill="none"
      className="shrink-0 text-[var(--accent)]"
    >
      {/* upper prong */}
      <path d={`${topProngPath} L 0,${prong} Z`} fill="currentColor" />
      {/* lower prong */}
      <path d={`${botProngPath} L 0,${prong + gap} Z`} fill="currentColor" />
    </svg>
  )
}

export function ToolCallBlock({ pair, onFileClick, bubbleHeightPx }: Props) {
  const [expanded, setExpanded] = useState(false)
  const adapter = getAdapter(pair.tool)

  const digest = pair.result && adapter ? adapter.summarize(pair.params, pair.result) : null
  const nodes  = pair.result && adapter ? adapter.toHierarchy(pair.params, pair.result) : []
  const expandedHeight = Math.floor(bubbleHeightPx * 0.6)

  const isRunning = pair.status === 'streaming'

  return (
    <div className="my-1.5">
      {/* ── Wrench shape ─────────────────────────────── */}
      <div
        className="flex items-center"
        style={{ height: SHAFT_H }}
        onClick={() => !isRunning && nodes.length > 0 && setExpanded(e => !e)}
      >
        {/* Left: ratchet circle with atom logo */}
        <div
          className="shrink-0 rounded-full border-2 border-[var(--accent)] flex items-center justify-center z-10"
          style={{
            width: SHAFT_H,
            height: SHAFT_H,
            background: 'var(--glass-bg)',
            backdropFilter: 'blur(8px)',
            marginRight: -1,
          }}
        >
          <Icon name="atom" size={Math.round(SHAFT_H * 0.55)} className="text-[var(--accent)]" />
        </div>

        {/* Center: shaft with tool name + status */}
        <div
          className={`flex flex-1 items-center gap-2 px-3 h-full min-w-0 ${nodes.length > 0 && !isRunning ? 'cursor-pointer' : 'cursor-default'}`}
          style={{
            background: 'var(--glass-bg-solid)',
            backdropFilter: 'blur(8px)',
            borderTop: '1.5px solid var(--accent)',
            borderBottom: '1.5px solid var(--accent)',
          }}
        >
          <span className="font-mono text-xs font-semibold text-[var(--accent)] shrink-0">
            {pair.tool}
          </span>

          {digest && !isRunning && (
            <>
              <span className="text-[var(--text-muted)] opacity-40 shrink-0">·</span>
              <span className="font-mono text-xs text-[var(--text-muted)] truncate">{digest}</span>
            </>
          )}

          <span
            className={`font-mono text-xs ml-auto shrink-0 ${
              isRunning ? 'text-[var(--accent)] animate-pulse' : 'text-[var(--text-muted)] opacity-60'
            }`}
          >
            {isRunning ? 'running…' : '✓ done'}
          </span>

          {nodes.length > 0 && !isRunning && (
            <span className="text-[9px] text-[var(--text-muted)] shrink-0 opacity-60">
              {expanded ? '▲' : '▼'}
            </span>
          )}
        </div>

        {/* Right: open-end jaw */}
        <WrenchJaw />
      </div>

      {/* ── Expanded detail panel ─────────────────────── */}
      {expanded && nodes.length > 0 && (
        <div
          className="overflow-y-auto px-3 pb-2 mt-1 rounded-lg border"
          style={{
            maxHeight: `${expandedHeight}px`,
            borderColor: 'color-mix(in srgb, var(--accent) 20%, transparent)',
            background: 'var(--glass-bg-solid)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <HierarchyRenderer nodes={nodes} onFileClick={onFileClick} />
        </div>
      )}
    </div>
  )
}
