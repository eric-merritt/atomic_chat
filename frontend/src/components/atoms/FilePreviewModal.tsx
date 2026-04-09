// frontend/src/components/atoms/FilePreviewModal.tsx
import { useState, useEffect } from 'react'
import { Highlight, themes } from 'prism-react-renderer'
import type { Language } from 'prism-react-renderer'

type Tab = 'doc' | 'summary' | 'json'

interface FileData {
  content: string
  language: string
  size_bytes: number
  lines_returned: number
  truncated: boolean
}

interface Props {
  path: string
  toolResult?: unknown
  onClose: () => void
}

const IMAGE_EXTS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico'])

function getExt(path: string): string {
  return path.slice(path.lastIndexOf('.')).toLowerCase()
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

// prism-react-renderer uses a subset of Prism language names
const PRISM_LANG_MAP: Record<string, Language> = {
  python: 'python', typescript: 'typescript', javascript: 'javascript',
  json: 'json', markdown: 'markdown', css: 'css', html: 'markup',
  bash: 'bash', rust: 'rust', go: 'go', java: 'java',
  c: 'c', cpp: 'cpp', sql: 'sql', yaml: 'yaml', toml: 'toml',
}

export function FilePreviewModal({ path, toolResult, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('doc')
  const [fileData, setFileData] = useState<FileData | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const isImg = IMAGE_EXTS.has(getExt(path))

  useEffect(() => {
    if (isImg) return
    setLoading(true)
    setFetchError(null)
    fetch(`/api/files/read?path=${encodeURIComponent(path)}`, { credentials: 'include' })
      .then(r => r.json())
      .then(data => { data.error ? setFetchError(data.error) : setFileData(data) })
      .catch(e => setFetchError(String(e)))
      .finally(() => setLoading(false))
  }, [path, isImg])

  const tabs: { id: Tab; icon: string; label: string }[] = [
    { id: 'doc',     icon: '🖹', label: 'Document' },
    { id: 'summary', icon: '📋', label: 'Summary'  },
    { id: 'json',    icon: '{}', label: 'JSON'     },
  ]

  function renderDoc() {
    if (isImg) {
      return (
        <div className="flex items-center justify-center h-full p-4">
          <img
            src={`/api/files/serve?path=${encodeURIComponent(path)}`}
            alt={path}
            className="max-w-full max-h-full object-contain"
          />
        </div>
      )
    }
    if (loading) return <div className="p-4 text-xs text-[var(--text-muted)]">Loading…</div>
    if (fetchError) return <div className="p-4 text-xs text-[var(--danger)]">Error: {fetchError}</div>
    if (!fileData) return null

    const prismLang = (PRISM_LANG_MAP[fileData.language] ?? 'text') as Language

    return (
      <div className="overflow-auto h-full p-4">
        <Highlight theme={themes.vsDark} code={fileData.content} language={prismLang}>
          {({ tokens, getLineProps, getTokenProps }) => (
            <pre className="font-mono text-xs leading-5 m-0" style={{ background: 'transparent' }}>
              {tokens.map((line, i) => (
                <div key={i} {...getLineProps({ line })} className="flex">
                  <span className="select-none text-right pr-4 opacity-30 w-10 shrink-0">
                    {i + 1}
                  </span>
                  <span>
                    {line.map((token, key) => (
                      <span key={key} {...getTokenProps({ token })} />
                    ))}
                  </span>
                </div>
              ))}
            </pre>
          )}
        </Highlight>
        {fileData.truncated && (
          <div className="mt-2 text-xs text-[var(--text-muted)] opacity-50">
            … truncated at {fileData.lines_returned} lines
          </div>
        )}
      </div>
    )
  }

  function renderSummary() {
    if (isImg) {
      return (
        <div className="p-4 font-mono text-xs text-[var(--text-muted)] space-y-1">
          <div><span className="text-[var(--accent)]">path   </span>{path}</div>
          <div><span className="text-[var(--accent)]">type   </span>image ({getExt(path)})</div>
        </div>
      )
    }
    if (!fileData) return null
    return (
      <div className="p-4 font-mono text-xs text-[var(--text-muted)] space-y-1">
        <div><span className="text-[var(--accent)]">path     </span>{path}</div>
        <div><span className="text-[var(--accent)]">language </span>{fileData.language}</div>
        <div><span className="text-[var(--accent)]">size     </span>{formatBytes(fileData.size_bytes)}</div>
        <div><span className="text-[var(--accent)]">lines    </span>
          {fileData.lines_returned}{fileData.truncated ? ' (truncated)' : ''}
        </div>
      </div>
    )
  }

  function renderJson() {
    return (
      <div className="overflow-auto h-full p-4">
        <pre className="font-mono text-xs text-[var(--text-muted)] whitespace-pre-wrap break-words m-0">
          {JSON.stringify(toolResult ?? null, null, 2)}
        </pre>
      </div>
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'color-mix(in srgb, var(--bg-base) 60%, transparent)' }}
      onClick={onClose}
    >
      {/* Modal — letter-size proportion, 60vw wide */}
      <div
        className="relative flex flex-col rounded-2xl overflow-hidden"
        style={{
          width: '60vw',
          height: 'min(calc(60vw * 1.294), 90vh)',
          background: 'color-mix(in srgb, var(--accent) 8%, transparent)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1.5px solid color-mix(in srgb, var(--accent) 60%, transparent)',
          boxShadow: [
            '0 0 40px color-mix(in srgb, var(--accent) 35%, transparent)',
            '0 0 80px color-mix(in srgb, var(--accent) 15%, transparent)',
          ].join(', '),
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-2 shrink-0 font-mono text-xs"
          style={{ borderBottom: '1px solid color-mix(in srgb, var(--accent) 20%, transparent)' }}
        >
          <span className="text-[var(--accent)] opacity-80 truncate">{path}</span>
          <button
            onClick={onClose}
            className="ml-4 shrink-0 text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-1 overflow-hidden">
          {/* Tab strip */}
          <div
            className="flex flex-col items-center gap-1 py-3 shrink-0"
            style={{
              width: '2.5rem',
              borderRight: '1px solid color-mix(in srgb, var(--accent) 20%, transparent)',
            }}
          >
            {tabs.map(t => (
              <button
                key={t.id}
                title={t.label}
                onClick={() => setActiveTab(t.id)}
                className="w-8 h-8 rounded-lg text-sm flex items-center justify-center transition-all duration-200"
                style={{
                  background: activeTab === t.id
                    ? 'color-mix(in srgb, var(--accent) 25%, transparent)'
                    : 'transparent',
                  color: activeTab === t.id ? 'var(--accent)' : 'var(--text-muted)',
                  boxShadow: activeTab === t.id
                    ? '0 0 8px color-mix(in srgb, var(--accent) 40%, transparent)'
                    : 'none',
                }}
              >
                {t.icon}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-hidden">
            {activeTab === 'doc'     && renderDoc()}
            {activeTab === 'summary' && renderSummary()}
            {activeTab === 'json'    && renderJson()}
          </div>
        </div>
      </div>
    </div>
  )
}
