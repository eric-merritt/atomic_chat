// frontend/src/components/molecules/MessageBubble.tsx
import { useState } from 'react'
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
            'whitespace-pre-wrap break-words font-mono font-light',
            'text-[var(--accent)] animate-[msgIn_0.25s_ease-out] relative',
            roleClasses[message.role] ?? '',
            message.role === 'assistant'
              ? isExpanded ? 'max-h-[800px]' : 'max-h-[250px]'
              : '',
          ].join(' ')}
        >
          {message.role === 'assistant' && message.toolPairs.map((pair, i) => (
            <ToolCallBlock
              key={i}
              pair={pair}
              bubbleHeightPx={400}
              onFileClick={(path) => {
                setPreviewPath(path)
                setPreviewResult(pair.result)
              }}
            />
          ))}

          {message.content}

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
