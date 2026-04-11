// frontend/src/components/molecules/MessageBubble.tsx
import { useState } from 'react'
import type React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message } from '../../atoms/message'
import { ToolCallBlock } from './ToolCallBlock'
import { FilePreviewModal } from '../atoms/FilePreviewModal'

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

export function MessageBubble({ message }: Props) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [previewPath, setPreviewPath] = useState<string | null>(null)
  const [previewResult, setPreviewResult] = useState<unknown>(null)

  return (
    <>
      <div className="px-4 py-3">
        <div
          className={[
            'overflow-y-auto max-w-[75%] px-4 py-3 rounded-xl text-sm leading-relaxed',
            'break-words text-[var(--accent)] animate-[msgIn_0.25s_ease-out] relative',
            roleClasses[message.role] ?? '',
            message.role === 'assistant'
              ? isExpanded ? 'max-h-[800px]' : 'max-h-[250px]'
              : '',
          ].join(' ')}
        >
          {message.role === 'assistant' ? (() => {
            const sorted = [...message.toolPairs].sort((a, b) => a.contentOffset - b.contentOffset)
            const nodes: React.ReactNode[] = []
            let cursor = 0
            sorted.forEach((pair, i) => {
              const offset = pair.contentOffset
              if (offset > cursor) {
                const slice = message.content.slice(cursor, offset)
                nodes.push(<div key={`text-${i}`} className="prose-md"><ReactMarkdown {...mdProps}>{slice}</ReactMarkdown></div>)
              }
              nodes.push(
                <ToolCallBlock
                  key={`tool-${i}`}
                  pair={pair}
                  bubbleHeightPx={400}
                  onFileClick={(path) => { setPreviewPath(path); setPreviewResult(pair.result) }}
                />
              )
              cursor = offset
            })
            if (cursor < message.content.length) {
              nodes.push(<div key="text-tail" className="prose-md"><ReactMarkdown {...mdProps}>{message.content.slice(cursor)}</ReactMarkdown></div>)
            }
            return nodes
          })() : <div className="prose-md"><ReactMarkdown {...mdProps}>{message.content}</ReactMarkdown></div>}

          {message.role === 'assistant' && (message.toolPairs.length > 0 || message.content.length > 300) && (
            <button
              onClick={() => setIsExpanded(e => !e)}
              className="absolute top-2 right-2 text-sm text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors cursor-pointer"
            >
              {isExpanded ? '▼' : '▲'}
            </button>
          )}
        </div>
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
