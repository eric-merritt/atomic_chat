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

// ── Geometry ────────────────────────────────────────────────
const CIRCLE_D   = 36                // diameter of both circles
const BAR_H      = 20                // shaft thickness (~¼ of CIRCLE_D)
const BORDER_W   = 5                // left circle ring thickness (triple of the previous 4)

// Right cap: solid filled circle with a horizontal rectangular cutout.
// Cut: 55% of diameter tall, vertically centered, starting 35% from left edge
// and running out to the right edge (the "open end" opening).
function RightCircle() {
  const d = CIRCLE_D
  const r = d / 2
  const cutH = Math.round(d * 0.50)
  const cutY = Math.round((d - cutH) / 2)
  const cutX = Math.round((d * 0.35) + 2)

  const circle = `M 0,${r} A ${r},${r},0,1,0,${d},${r} A ${r},${r},0,1,0,0,${r} Z`
  const cut    = `M ${cutX},${cutY} L ${d},${cutY} L ${d},${cutY + cutH} L ${cutX},${cutY + cutH} Z`

  return (
    <svg width={d} height={d} viewBox={`0 0 ${d} ${d}`} className="shrink-0 text-[var(--accent)]">
      <path d={`${circle}`} fill="currentColor" fillRule="evenodd" />
      <path d={`${cut}`} fill="#100818" fillRule="evenodd" />
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
    <div className="my-3" style={{ maxWidth: 240 }}>
      <div
        className="relative flex items-center"
        style={{ height: CIRCLE_D }}
        onClick={() => !isRunning && nodes.length > 0 && setExpanded(e => !e)}
      >
        {/* 1. Left circle — triple-thick ring with atom logo centered in the inner hole */}
        <div
          className="shrink-0 rounded-full flex items-center justify-center"
          style={{
            width: CIRCLE_D,
            height: CIRCLE_D,
            border: `${BORDER_W}px solid var(--accent)`,
            background: 'var(--bg-base)',
            marginRight: -4,
            zIndex: 2,
          }}
        >
          <Icon
            name="atom"
            size={Math.max(8, CIRCLE_D - BORDER_W * 2 - 2)}
            className="text-[var(--accent)]"
          />
        </div>

        {/* 2. Shaft — thin bar vertically centered; clear text strip in the middle 50% (inset, not full-width) */}
        <div
          className={`flex items-center flex-1 h-full ${nodes.length > 0 && !isRunning ? 'cursor-pointer' : 'cursor-default'}`}
        >
          {/* Solid accent bar, centered vertically */}
          <div className={'bg-[var(--accent)] items-center w-[176px] p-0'} style={{
              height: BAR_H,
            }}
          >
          {/* Clear text strip — inset from both shaft ends */}
          <div
            className="absolute flex items-center py-none m-auto"
            style={{
              bottom: '30%',
              left: '25%',
              width: `50%`,
              height: 0.7 * BAR_H,
              background: 'var(--bg-base)',
              paddingLeft: 6,
              paddingRight: 6,
              paddingTop: -1,
              paddingBottom: -1,
              alignSelf: 'center',
            }}
          >
            
            <span
              className="font-mono font-bold text-[var(--accent)] shrink-0 truncate leading-none"
              style={{ fontSize: 8 }}
            >
              {pair.tool}
            </span>
            {digest && !isRunning && (
              <span
                className="font-mono text-[var(--accent)] opacity-60 truncate leading-none"
                style={{ fontSize: 6 }}
              >
                · {digest}
              </span>
            )}
            <span
              className={`font-mono ml-auto shrink-0 text-[var(--accent)] leading-none ${isRunning ? 'animate-pulse' : 'opacity-70'}`}
              style={{ fontSize: 8 }}
            >
              {isRunning ? '…' : '✓'}
            </span>
          </div>
          </div>
        </div>

        {/* 3. Right: solid circle with rectangular slot cut out horizontally */}
        <div className="shrink-0 bg-[var(--base)]" style={{ marginLeft: -4, zIndex: 2 }}>
          <RightCircle />
        </div>
      </div>

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
