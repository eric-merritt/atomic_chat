import { useState } from 'react'
import type React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, ToolCallPair } from '../../atoms/message'
import { ToolCallBlock } from './ToolCallBlock'
import { FilePreviewModal } from '../atoms/FilePreviewModal'
import { ApGallery, type ApGalleryPayload } from '../organisms/ApGallery'
import { Icon } from '../atoms/Icon'
import { useWorkspace } from '../../hooks/useWorkspace'

interface Props {
  message: Message
}

const roleClasses: Record<string, string> = {
  user:      'self-end bg-[var(--msg-user)]',
  assistant: 'self-start bg-[var(--msg-assistant)]',
  error:     'self-center bg-transparent text-[var(--danger)] text-center',
}

const mdComponents = {
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
    const text = String(children ?? '')
    const display = (!text || text === 'Link') ? (href ?? '') : text
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="underline text-[var(--accent)] hover:brightness-125">
        {display}
      </a>
    )
  }
}

const mdProps = { remarkPlugins: [remarkGfm], components: mdComponents }

function InlineGallery({ payload }: { payload: ApGalleryPayload }) {
  const { showGallery } = useWorkspace()
  return (
    <div className="my-2 self-start max-w-[75%]">
      <ApGallery
        payload={payload}
        columns={3}
        leftRail={
          <button
            onClick={() => showGallery(payload)}
            title="Open in workspace"
            className="text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer p-1"
          >
            <Icon name="grid3" size={18} />
          </button>
        }
      />
    </div>
  )
}

function galleryPayload(pair: ToolCallPair): ApGalleryPayload | null {
  const result = pair.result as { data?: { type?: string; items?: unknown; caption?: string } } | null
  const data = result?.data
  if (!data || data.type !== 'ap_gallery' || !Array.isArray(data.items)) return null
  return { items: data.items as ApGalleryPayload['items'], caption: data.caption }
}

function TextBubble({
  role,
  content,
  showExpand,
}: {
  role: Message['role']
  content: string
  showExpand: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  if (!content.trim()) return null
  return (
    <div
      className={[
        'overflow-y-auto max-w-[75%] px-4 py-3 rounded-xl text-sm leading-relaxed mt-1',
        'break-words text-[var(--accent)] animate-[msgIn_0.25s_ease-out] relative',
        roleClasses[role] ?? '',
        role === 'assistant'
          ? expanded ? 'max-h-[800px]' : 'max-h-[250px]'
          : '',
      ].join(' ')}
    >
      <div className="prose-md">
        <ReactMarkdown {...mdProps}>{content}</ReactMarkdown>
      </div>
      {showExpand && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="absolute top-2 right-2 text-sm text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors cursor-pointer"
        >
          {expanded ? '▼' : '▲'}
        </button>
      )}
    </div>
  )
}

export function MessageBubble({ message }: Props) {
  const [previewPath, setPreviewPath] = useState<string | null>(null)
  const [previewResult, setPreviewResult] = useState<unknown>(null)

  // Walk all tool pairs in contentOffset order and interleave with text.
  // Each pair is rendered AFTER the text that was streamed before it was called
  // (a tool call sits below the reasoning that produced it, not above).
  const sortedPairs = [...message.toolPairs].sort(
    (a, b) => a.contentOffset - b.contentOffset
  )

  type Segment =
    | { kind: 'text'; content: string }
    | { kind: 'gallery'; payload: ApGalleryPayload }
    | { kind: 'tool'; pair: ToolCallPair }

  const segments: Segment[] = []
  let cursor = 0
  for (const pair of sortedPairs) {
    const offset = Math.min(pair.contentOffset, message.content.length)
    if (offset > cursor) {
      segments.push({ kind: 'text', content: message.content.slice(cursor, offset) })
    }
    const payload = galleryPayload(pair)
    if (payload) segments.push({ kind: 'gallery', payload })
    else segments.push({ kind: 'tool', pair })
    cursor = offset
  }
  if (cursor < message.content.length) {
    segments.push({ kind: 'text', content: message.content.slice(cursor) })
  } else if (segments.length === 0 && message.content.length > 0) {
    segments.push({ kind: 'text', content: message.content })
  }

  return (
    <>
      <div className="px-4 py-1">
        {segments.map((seg, i) => {
          if (seg.kind === 'gallery') {
            return <InlineGallery key={`seg-${i}`} payload={seg.payload} />
          }
          if (seg.kind === 'tool') {
            return (
              <ToolCallBlock
                key={`seg-${i}`}
                pair={seg.pair}
                bubbleHeightPx={400}
                onFileClick={(path) => { setPreviewPath(path); setPreviewResult(seg.pair.result) }}
              />
            )
          }
          return (
            <TextBubble
              key={`seg-${i}`}
              role={message.role}
              content={seg.content}
              showExpand={message.role === 'assistant' && seg.content.length > 300}
            />
          )
        })}
      </div>

      {previewPath && (
        <FilePreviewModal
          path={previewPath}
          toolResult={previewResult}
          onClose={() => setPreviewPath(null)}
        />
      )}
    </>
  )
}
