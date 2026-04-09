# Tool Result Renderers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the aggregate ToolCallPanel with per-call ToolCallBlocks inside agent MessageBubbles, add a universal HierarchyRenderer for structured tool results, and build a futuristic frosted-glass FilePreviewModal.

**Architecture:** Tool call/result stream events are paired per-message in ChatProvider into `ToolCallPair[]` on each `Message`. MessageBubble renders one `ToolCallBlock` per pair in streaming→digest→expanded states. A shared `toolAdapters.ts` module transforms raw JSON into `HierarchyNode[]`. FilePreviewModal fetches file content from a new `/api/files/read` endpoint and renders syntax-highlighted code using `prism-react-renderer` (React-native, no raw HTML injection).

**Tech Stack:** React 18, TypeScript, Tailwind v4 CSS variables, prism-react-renderer (syntax highlighting), Flask (new file blueprint), pytest (backend tests), vitest + @testing-library/react (frontend tests)

---

## File Map

**Create:**
- `routes/files.py` — file read/serve Flask blueprint
- `tests/test_routes_files.py` — backend tests
- `frontend/src/lib/toolAdapters.ts` — summarize + toHierarchy per tool
- `frontend/src/lib/__tests__/toolAdapters.test.ts`
- `frontend/src/components/atoms/HierarchyRenderer.tsx`
- `frontend/src/components/atoms/__tests__/HierarchyRenderer.test.tsx`
- `frontend/src/components/atoms/FilePreviewModal.tsx`
- `frontend/src/components/molecules/ToolCallBlock.tsx`

**Modify:**
- `main.py` — register files blueprint
- `frontend/src/atoms/message.ts` — add `ToolCallPair`, add `toolPairs` to `Message`
- `frontend/src/providers/ChatProvider.tsx` — populate `toolPairs` per message
- `frontend/src/components/molecules/MessageBubble.tsx` — render ToolCallBlocks, fix scroll
- `frontend/src/components/organisms/MessageList.tsx` — add scroll tracking + Jump to current

**Delete:**
- `frontend/src/components/atoms/ToolCallPanel.tsx` — replaced by ToolCallBlock

---

## Task 1: Backend file endpoints

**Files:**
- Create: `routes/files.py`
- Create: `tests/test_routes_files.py`
- Modify: `main.py` (register blueprint)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_routes_files.py
import os
import pytest
from main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    with app.test_client() as c:
        yield c

def test_read_missing_path(client):
    r = client.get('/api/files/read')
    assert r.status_code == 400

def test_read_nonexistent_file(client, tmp_path):
    r = client.get(f'/api/files/read?path={tmp_path}/nope.py')
    assert r.status_code == 404

def test_read_python_file(client, tmp_path):
    f = tmp_path / 'hello.py'
    f.write_text('x = 1\n' * 5)
    r = client.get(f'/api/files/read?path={f}')
    assert r.status_code == 200
    data = r.get_json()
    assert data['language'] == 'python'
    assert 'x = 1' in data['content']
    assert data['truncated'] is False
    assert data['lines_returned'] == 5

def test_read_truncates_at_500_lines(client, tmp_path):
    f = tmp_path / 'big.py'
    f.write_text('x = 1\n' * 600)
    r = client.get(f'/api/files/read?path={f}')
    data = r.get_json()
    assert data['truncated'] is True
    assert data['lines_returned'] == 500

def test_read_traversal_rejected(client):
    r = client.get('/api/files/read?path=/etc/../etc/passwd')
    assert r.status_code == 403

def test_serve_image(client, tmp_path):
    img = tmp_path / 'photo.png'
    img.write_bytes(b'\x89PNG\r\n\x1a\n')
    r = client.get(f'/api/files/serve?path={img}')
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_routes_files.py -v
```
Expected: ImportError or 404s — `files_bp` not registered yet.

- [ ] **Step 3: Create `routes/files.py`**

```python
"""File read and serve endpoints for the frontend file preview modal."""

import os
from flask import Blueprint, jsonify, request, send_file
from flask_login import login_required

files_bp = Blueprint("files", __name__, url_prefix="/api/files")

LANGUAGE_MAP = {
    '.py': 'python', '.ts': 'typescript', '.tsx': 'typescript',
    '.js': 'javascript', '.jsx': 'javascript', '.json': 'json',
    '.md': 'markdown', '.html': 'html', '.css': 'css',
    '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash',
    '.yml': 'yaml', '.yaml': 'yaml', '.toml': 'toml',
    '.rs': 'rust', '.go': 'go', '.java': 'java',
    '.c': 'c', '.cpp': 'cpp', '.h': 'c',
    '.sql': 'sql', '.ini': 'ini', '.env': 'bash',
    '.txt': 'text', '.log': 'text', '.xml': 'xml',
}

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico'}

MAX_LINES = 500


def _safe_path(path: str) -> str | None:
    """Resolve path and reject traversal attempts."""
    if not path:
        return None
    parts = path.replace('\\', '/').split('/')
    if '..' in parts:
        return None
    return os.path.realpath(os.path.expanduser(path))


@files_bp.route("/read")
@login_required
def read_file():
    path = request.args.get("path", "")
    resolved = _safe_path(path)
    if not path:
        return jsonify({"error": "path required"}), 400
    if not resolved:
        return jsonify({"error": "invalid path"}), 403
    if not os.path.isfile(resolved):
        return jsonify({"error": "not found"}), 404

    ext = os.path.splitext(resolved)[1].lower()
    if ext in IMAGE_EXTS:
        return jsonify({"error": "use /api/files/serve for images"}), 400

    language = LANGUAGE_MAP.get(ext, "text")

    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except PermissionError:
        return jsonify({"error": "permission denied"}), 403

    truncated = len(lines) > MAX_LINES
    content = "".join(lines[:MAX_LINES])

    return jsonify({
        "content": content,
        "language": language,
        "size_bytes": os.path.getsize(resolved),
        "lines_returned": min(len(lines), MAX_LINES),
        "truncated": truncated,
    })


@files_bp.route("/serve")
@login_required
def serve_file():
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path required"}), 400
    resolved = _safe_path(path)
    if not resolved:
        return jsonify({"error": "invalid path"}), 403
    if not os.path.isfile(resolved):
        return jsonify({"error": "not found"}), 404
    return send_file(resolved)
```

- [ ] **Step 4: Register blueprint in `main.py`**

Find the block where other blueprints are registered (search for `register_blueprint`). Add:

```python
from routes.files import files_bp
# after existing blueprint registrations:
app.register_blueprint(files_bp)
```

- [ ] **Step 5: Run tests — confirm they pass**

```bash
uv run pytest tests/test_routes_files.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add routes/files.py tests/test_routes_files.py main.py
git commit -m "feat: add /api/files/read and /api/files/serve endpoints"
```

---

## Task 2: HierarchyNode type + HierarchyRenderer

**Files:**
- Create: `frontend/src/components/atoms/HierarchyRenderer.tsx`
- Create: `frontend/src/components/atoms/__tests__/HierarchyRenderer.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/atoms/__tests__/HierarchyRenderer.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HierarchyRenderer } from '../HierarchyRenderer'
import type { HierarchyNode } from '../HierarchyRenderer'

const nodes: HierarchyNode[] = [
  { label: '/src/config.py', depth: 0, isFile: true, href: '/src/config.py' },
  { label: 'line 14: x = 1', depth: 1, isFile: false },
  { label: 'Stack Overflow | stackoverflow.com', depth: 0, isFile: false, isExternal: true, href: 'https://stackoverflow.com' },
]

test('renders all labels', () => {
  render(<HierarchyRenderer nodes={nodes} onFileClick={() => {}} />)
  expect(screen.getByText(/line 14: x = 1/)).toBeInTheDocument()
  expect(screen.getByText('/src/config.py')).toBeInTheDocument()
})

test('file node calls onFileClick with href', async () => {
  const onClick = vi.fn()
  render(<HierarchyRenderer nodes={nodes} onFileClick={onClick} />)
  await userEvent.click(screen.getByText('/src/config.py'))
  expect(onClick).toHaveBeenCalledWith('/src/config.py')
})

test('external node renders as anchor with target blank', () => {
  render(<HierarchyRenderer nodes={nodes} onFileClick={() => {}} />)
  const link = screen.getByText(/Stack Overflow/)
  expect(link.tagName).toBe('A')
  expect(link).toHaveAttribute('href', 'https://stackoverflow.com')
  expect(link).toHaveAttribute('target', '_blank')
})
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd frontend && npx vitest run src/components/atoms/__tests__/HierarchyRenderer.test.tsx
```
Expected: FAIL — module not found.

- [ ] **Step 3: Create `HierarchyRenderer.tsx`**

```tsx
// frontend/src/components/atoms/HierarchyRenderer.tsx

export interface HierarchyNode {
  label: string
  depth: number        // indent = depth * 2 non-breaking spaces
  isFile: boolean      // underline + onFileClick handler
  href?: string        // file path (isFile) or URL (isExternal)
  isExternal?: boolean // open in new tab
}

interface Props {
  nodes: HierarchyNode[]
  onFileClick: (path: string) => void
}

export function HierarchyRenderer({ nodes, onFileClick }: Props) {
  return (
    <div className="font-mono text-xs leading-relaxed">
      {nodes.map((node, i) => {
        const pad = '\u00A0'.repeat(node.depth * 2)

        if (node.isExternal && node.href) {
          return (
            <div key={i} className="text-[var(--text-muted)]">
              {pad}
              <a
                href={node.href}
                target="_blank"
                rel="noopener noreferrer"
                className="underline text-[var(--accent)] hover:brightness-125 transition-[filter]"
              >
                {node.label}
              </a>
            </div>
          )
        }

        if (node.isFile && node.href) {
          return (
            <div key={i} className="text-[var(--text-muted)]">
              {pad}
              <span
                className="underline text-[var(--accent)] hover:brightness-125 transition-[filter] cursor-pointer"
                onClick={() => onFileClick(node.href!)}
              >
                {node.label}
              </span>
            </div>
          )
        }

        return (
          <div key={i} className="text-[var(--text-muted)]">
            {pad}{node.label}
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd frontend && npx vitest run src/components/atoms/__tests__/HierarchyRenderer.test.tsx
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/atoms/HierarchyRenderer.tsx \
        frontend/src/components/atoms/__tests__/HierarchyRenderer.test.tsx
git commit -m "feat: add HierarchyRenderer atom and HierarchyNode type"
```

---

## Task 3: toolAdapters.ts

**Files:**
- Create: `frontend/src/lib/toolAdapters.ts`
- Create: `frontend/src/lib/__tests__/toolAdapters.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// frontend/src/lib/__tests__/toolAdapters.test.ts
import { getAdapter } from '../toolAdapters'

test('fs_grep summarize', () => {
  const a = getAdapter('fs_grep')!
  const data = { pattern: 'config', count: 14, matches: [
    { file: '/src/a.py', line: 1, snippet: '  >     1  x' },
    { file: '/src/b.py', line: 5, snippet: '  >     5  y' },
  ], truncated: false }
  expect(a.summarize({}, data)).toBe("Found 14 matches for 'config' across 2 files")
})

test('fs_grep toHierarchy groups by file', () => {
  const a = getAdapter('fs_grep')!
  const data = { pattern: 'config', count: 2, matches: [
    { file: '/src/a.py', line: 3, snippet: '  >     3  x = config()' },
    { file: '/src/a.py', line: 7, snippet: '  >     7  y = config()' },
    { file: '/src/b.py', line: 1, snippet: '  >     1  import config' },
  ], truncated: false }
  const nodes = a.toHierarchy({}, data)
  expect(nodes[0]).toMatchObject({ label: '/src/a.py', depth: 0, isFile: true, href: '/src/a.py' })
  expect(nodes[1]).toMatchObject({ label: 'line 3: x = config()', depth: 1, isFile: false })
  expect(nodes[2]).toMatchObject({ label: 'line 7: y = config()', depth: 1, isFile: false })
  expect(nodes[3]).toMatchObject({ label: '/src/b.py', depth: 0, isFile: true })
})

test('fs_find summarize', () => {
  const a = getAdapter('fs_find')!
  const data = { path: '/src', count: 8, files: ['/src/a.py'] }
  expect(a.summarize({}, data)).toBe('Found 8 files in /src')
})

test('fs_find toHierarchy flat file list', () => {
  const a = getAdapter('fs_find')!
  const data = { path: '/src', count: 2, files: ['/src/a.py', '/src/b.py'] }
  const nodes = a.toHierarchy({}, data)
  expect(nodes).toHaveLength(2)
  expect(nodes[0]).toMatchObject({ label: '/src/a.py', depth: 0, isFile: true, href: '/src/a.py' })
})

test('www_ddg summarize', () => {
  const a = getAdapter('www_ddg')!
  const data = { abstract: '', abstract_url: '', results: [{text:'a',url:'http://x.com'},{text:'b',url:'http://y.com'}] }
  expect(a.summarize({ query: 'python config' }, data)).toBe('Web search: 2 results')
})

test('www_ddg toHierarchy builds external links', () => {
  const a = getAdapter('www_ddg')!
  const data = { abstract: '', abstract_url: '', results: [
    { text: 'How to configure Python', url: 'https://docs.python.org/config' },
  ]}
  const nodes = a.toHierarchy({ query: 'python config' }, data)
  expect(nodes[0]).toMatchObject({ label: 'python config — 1 results', depth: 0, isFile: false })
  expect(nodes[1]).toMatchObject({ isExternal: true, depth: 0, href: 'https://docs.python.org/config' })
  expect(nodes[2]).toMatchObject({ label: 'How to configure Python', depth: 1, isFile: false })
})

test('www_fetch summarize', () => {
  const a = getAdapter('www_fetch')!
  const data = { ref: 'abc123', url: 'https://example.com', title: 'Example', size_chars: 45000 }
  expect(a.summarize({}, data)).toBe('Fetched example.com — ref abc123, 45000 chars')
})

test('www_get summarize', () => {
  const a = getAdapter('www_get')!
  const data = { ref: 'abc123', url: 'https://x.com', selector: '.price', count: 12, results: [] }
  expect(a.summarize({}, data)).toBe("12 elements matching '.price'")
})

test('getAdapter returns null for unknown tool', () => {
  expect(getAdapter('unknown_tool')).toBeNull()
})
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd frontend && npx vitest run src/lib/__tests__/toolAdapters.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Create `frontend/src/lib/toolAdapters.ts`**

```ts
// frontend/src/lib/toolAdapters.ts
import type { HierarchyNode } from '../components/atoms/HierarchyRenderer'

export interface ToolAdapter {
  summarize(params: unknown, data: unknown): string
  toHierarchy(params: unknown, data: unknown): HierarchyNode[]
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function asObj(v: unknown): Record<string, unknown> {
  return (v && typeof v === 'object' && !Array.isArray(v))
    ? (v as Record<string, unknown>) : {}
}
function asArr(v: unknown): unknown[] { return Array.isArray(v) ? v : [] }
function asStr(v: unknown, fb = ''): string { return typeof v === 'string' ? v : fb }
function asNum(v: unknown, fb = 0): number { return typeof v === 'number' ? v : fb }

function hostname(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
}

/** Extract code from a grep snippet line: "  >     14  x = config()" → "x = config()" */
function parseSnippetLine(snippet: string): string {
  const m = snippet.match(/>\s+\d+\s+(.*)/)
  return m ? m[1].trim() : snippet.trim()
}

// ── fs_tree ──────────────────────────────────────────────────────────────────

/**
 * lsd --tree output uses box-drawing characters (├── └── │).
 * Each depth level adds 4 chars of prefix before the item name.
 */
function parseTree(tree: string, rootPath: string): HierarchyNode[] {
  const nodes: HierarchyNode[] = []
  const pathStack: string[] = []

  for (const line of tree.split('\n')) {
    const nameMatch = line.match(/[^\s│├└─]/)
    if (!nameMatch) continue
    const depth = Math.floor((nameMatch.index ?? 0) / 4)
    const name = line.slice(nameMatch.index!).trim()
    const isDir = name.endsWith('/')
    const cleanName = name.replace(/\/$/, '')

    pathStack.length = depth
    const parent = depth === 0 ? rootPath : (pathStack[depth - 1] ?? rootPath)
    const fullPath = `${parent}/${cleanName}`
    pathStack[depth] = fullPath

    nodes.push({ label: cleanName, depth, isFile: !isDir, href: isDir ? undefined : fullPath })
  }
  return nodes
}

const fsTree: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    const fileCount = asStr(d.tree).split('\n')
      .filter(l => l.trim() && !l.trim().endsWith('/')).length
    return `Directory tree: ${asStr(d.path, '?')} — ${fileCount} files`
  },
  toHierarchy(_p, data) {
    const d = asObj(data)
    return parseTree(asStr(d.tree), asStr(d.path))
  },
}

// ── fs_ls_dir ────────────────────────────────────────────────────────────────

const fsLsDir: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    return `Directory: ${asStr(d.path, '?')} — ${asArr(d.entries).length} entries`
  },
  toHierarchy(_p, data) {
    const d = asObj(data)
    const path = asStr(d.path)
    return asArr(d.entries).map(e => {
      const entry = asObj(e)
      const name = asStr(entry.name, String(e)).replace(/\/$/, '')
      const isDir = asStr(entry.type) === 'directory'
      return { label: name, depth: 0, isFile: !isDir, href: isDir ? undefined : `${path}/${name}` }
    })
  },
}

// ── fs_grep ──────────────────────────────────────────────────────────────────

const fsGrep: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    const files = new Set(asArr(d.matches).map(m => asStr(asObj(m).file))).size
    return `Found ${asNum(d.count)} matches for '${asStr(d.pattern)}' across ${files} files`
  },
  toHierarchy(_p, data) {
    const d = asObj(data)
    const nodes: HierarchyNode[] = []
    let lastFile = ''
    for (const m of asArr(d.matches)) {
      const match = asObj(m)
      const file = asStr(match.file)
      const line = asNum(match.line)
      const snippet = asStr(match.snippet)
      if (file !== lastFile) {
        nodes.push({ label: file, depth: 0, isFile: true, href: file })
        lastFile = file
      }
      nodes.push({ label: `line ${line}: ${parseSnippetLine(snippet)}`, depth: 1, isFile: false })
    }
    return nodes
  },
}

// ── fs_find ──────────────────────────────────────────────────────────────────

const fsFind: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    return `Found ${asNum(d.count)} files in ${asStr(d.path, '?')}`
  },
  toHierarchy(_p, data) {
    const d = asObj(data)
    return asArr(d.files).map(f => ({
      label: asStr(f), depth: 0, isFile: true, href: asStr(f),
    }))
  },
}

// ── www_ddg ──────────────────────────────────────────────────────────────────

const wwwDdg: ToolAdapter = {
  summarize(_p, data) {
    return `Web search: ${asArr(asObj(data).results).length} results`
  },
  toHierarchy(params, data) {
    const p = asObj(params)
    const d = asObj(data)
    const query = asStr(p.query, 'search')
    const results = asArr(d.results)
    const nodes: HierarchyNode[] = [
      { label: `${query} — ${results.length} results`, depth: 0, isFile: false },
    ]
    for (const r of results) {
      const result = asObj(r)
      const url = asStr(result.url)
      nodes.push({
        label: `${hostname(url)} | ${url}`,
        depth: 0, isFile: false, isExternal: true, href: url,
      })
      const text = asStr(result.text)
      if (text) nodes.push({ label: text, depth: 1, isFile: false })
    }
    return nodes
  },
}

// ── www_fetch ────────────────────────────────────────────────────────────────

const wwwFetch: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    return `Fetched ${hostname(asStr(d.url))} — ref ${asStr(d.ref)}, ${asNum(d.size_chars)} chars`
  },
  toHierarchy(_p, data) {
    const d = asObj(data)
    const url = asStr(d.url)
    return [{
      label: `${asStr(d.title, hostname(url))} (ref: ${asStr(d.ref)})`,
      depth: 0, isFile: false, isExternal: true, href: url,
    }]
  },
}

// ── www_get ──────────────────────────────────────────────────────────────────

const wwwGet: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    return `${asNum(d.count)} elements matching '${asStr(d.selector)}'`
  },
  toHierarchy(_p, data) {
    const d = asObj(data)
    return asArr(d.results).slice(0, 20).map((r, i) => ({
      label: asStr(r, `result ${i + 1}`), depth: 0, isFile: false,
    }))
  },
}

// ── Registry ─────────────────────────────────────────────────────────────────

const ADAPTERS: Record<string, ToolAdapter> = {
  fs_tree:   fsTree,
  fs_ls_dir: fsLsDir,
  fs_grep:   fsGrep,
  fs_find:   fsFind,
  www_ddg:   wwwDdg,
  www_fetch: wwwFetch,
  www_get:   wwwGet,
}

export function getAdapter(toolName: string): ToolAdapter | null {
  return ADAPTERS[toolName] ?? null
}
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd frontend && npx vitest run src/lib/__tests__/toolAdapters.test.ts
```
Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/toolAdapters.ts \
        frontend/src/lib/__tests__/toolAdapters.test.ts
git commit -m "feat: add toolAdapters with summarize+toHierarchy for fs and web tools"
```

---

## Task 4: ToolCallBlock molecule

**Files:**
- Create: `frontend/src/components/molecules/ToolCallBlock.tsx`

- [ ] **Step 1: Create `ToolCallBlock.tsx`**

```tsx
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/molecules/ToolCallBlock.tsx
git commit -m "feat: add ToolCallBlock with streaming/digest/expanded states"
```

---

## Task 5: FilePreviewModal

**Files:**
- Create: `frontend/src/components/atoms/FilePreviewModal.tsx`

- [ ] **Step 1: Install prism-react-renderer**

```bash
cd frontend && npm install prism-react-renderer
```

- [ ] **Step 2: Create `FilePreviewModal.tsx`**

```tsx
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
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/atoms/FilePreviewModal.tsx
git commit -m "feat: add FilePreviewModal with frosted neon glass design, prism syntax highlighting"
```

---

## Task 6: Message type + ChatProvider pairing

**Files:**
- Modify: `frontend/src/atoms/message.ts`
- Modify: `frontend/src/providers/ChatProvider.tsx`

- [ ] **Step 1: Update `message.ts`**

Open `frontend/src/atoms/message.ts`. Add `ToolCallPair` and update `Message` and factory functions.

> **Note:** `ToolCallPair` was temporarily defined inside `ToolCallBlock.tsx` in Task 4. After this step, update `ToolCallBlock.tsx` to remove its local definition and import `ToolCallPair` from `../../atoms/message` instead.

```ts
// Add after the ToolCallInfo interface:
export interface ToolCallPair {
  tool: string
  params: unknown        // parsed from tool_call input JSON string
  result: unknown | null // null until tool_result arrives
  status: 'streaming' | 'done'
}

// Update Message — add toolPairs:
export interface Message {
  id: string
  role: MessageRole
  content: string
  images: ImageAttachment[]
  toolCalls: ToolCallInfo[]  // kept for backward compat
  toolPairs: ToolCallPair[]  // new: paired call+result for rendering
  timestamp: number
}

// Update createMessage:
export function createMessage(role: MessageRole, content: string): Message {
  return {
    id: genId(), role, content, images: [],
    toolCalls: [], toolPairs: [], timestamp: Date.now(),
  }
}

// Update createMessageFromHistory:
export function createMessageFromHistory(entry: { role: string; content: string }): Message {
  return {
    id: genId(), role: entry.role as MessageRole, content: entry.content,
    images: [], toolCalls: [], toolPairs: [], timestamp: 0,
  }
}
```

- [ ] **Step 2: Update `ChatProvider.tsx` stream handler**

Find the `tool_call` and `tool_result` cases in the stream event switch/handler. Replace them:

```ts
case 'tool_call': {
  let params: unknown = ev.input
  try { params = JSON.parse(ev.input) } catch { /* keep raw string */ }

  setMessages(prev => {
    const msgs = [...prev]
    const last = msgs[msgs.length - 1]
    if (!last || last.role !== 'assistant') return prev
    return [
      ...msgs.slice(0, -1),
      {
        ...last,
        toolPairs: [
          ...last.toolPairs,
          { tool: ev.tool, params, result: null, status: 'streaming' as const },
        ],
      },
    ]
  })
  // Keep existing toolActivities for backward compat
  setToolActivities(prev => [...prev, {
    type: 'call' as const, tool: ev.tool, content: ev.input, timestamp: Date.now(),
  }])
  break
}

case 'tool_result': {
  let result: unknown = ev.output
  try { result = JSON.parse(ev.output) } catch { /* keep raw string */ }

  setMessages(prev => {
    const msgs = [...prev]
    const last = msgs[msgs.length - 1]
    if (!last || last.role !== 'assistant') return prev
    const pairs = [...last.toolPairs]
    // Find the last streaming entry for this tool
    const idx = [...pairs.keys()]
      .filter(i => pairs[i].tool === ev.tool && pairs[i].status === 'streaming')
      .at(-1)
    if (idx === undefined) return prev
    pairs[idx] = { ...pairs[idx], result, status: 'done' }
    return [...msgs.slice(0, -1), { ...last, toolPairs: pairs }]
  })
  setToolActivities(prev => [...prev, {
    type: 'result' as const, tool: ev.tool, content: ev.output, timestamp: Date.now(),
  }])
  break
}
```

- [ ] **Step 3: Run frontend tests**

```bash
cd frontend && npx vitest run
```

Fix any TypeScript errors — most will be `toolPairs` missing in test fixture objects. Add `toolPairs: []` to any `Message` mock objects in test files.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/atoms/message.ts frontend/src/providers/ChatProvider.tsx
git commit -m "feat: add ToolCallPair to Message, populate in ChatProvider stream handler"
```

---

## Task 7: MessageBubble + scroll behavior + remove ToolCallPanel

**Files:**
- Modify: `frontend/src/components/molecules/MessageBubble.tsx`
- Modify: `frontend/src/components/organisms/MessageList.tsx`
- Delete: `frontend/src/components/atoms/ToolCallPanel.tsx`

- [ ] **Step 1: Find MessageList and its scroll container**

```bash
grep -rn "MessageBubble\|ToolCallPanel\|overflow-y-auto" frontend/src/components/organisms/
```

Note which element in `MessageList.tsx` is the scrollable chat container (the outer div that holds all bubbles). You will add `ref` and `onScroll` to it.

- [ ] **Step 2: Add scroll tracking to `MessageList.tsx`**

In `MessageList.tsx`, add the following. Find the scrollable container div (from Step 1) and wire it up:

```tsx
// Add to imports at top of file:
import { useRef, useState, useCallback } from 'react'

// Add inside the component function body:
const listRef = useRef<HTMLDivElement>(null)
const [userScrolled, setUserScrolled] = useState(false)

const handleScroll = useCallback(() => {
  const el = listRef.current
  if (!el) return
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 40
  setUserScrolled(!atBottom)
}, [])

const jumpToCurrent = useCallback(() => {
  listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  setUserScrolled(false)
}, [])

// On the scrollable container div, add: ref={listRef} onScroll={handleScroll}
// e.g. <div ref={listRef} onScroll={handleScroll} className="... overflow-y-auto ...">

// Pass autoScroll to each MessageBubble:
// <MessageBubble key={msg.id} message={msg} autoScroll={!userScrolled} />

// Add Jump to current button inside the component return, as a sibling to the list container:
// Wrap both in a relative div if not already:
{userScrolled && (
  <button
    onClick={jumpToCurrent}
    className="absolute bottom-20 left-1/2 -translate-x-1/2 z-10 px-3 py-1.5 text-xs font-mono rounded-full transition-all duration-200 animate-[msgIn_0.2s_ease-out]"
    style={{
      background: 'color-mix(in srgb, var(--accent) 20%, transparent)',
      border: '1px solid color-mix(in srgb, var(--accent) 40%, transparent)',
      color: 'var(--accent)',
      boxShadow: '0 0 12px color-mix(in srgb, var(--accent) 30%, transparent)',
    }}
  >
    Jump to current ↓
  </button>
)}
```

- [ ] **Step 3: Rewrite `MessageBubble.tsx`**

Replace the entire file:

```tsx
// frontend/src/components/molecules/MessageBubble.tsx
import { useState, useEffect, useRef } from 'react'
import type { Message } from '../../atoms/message'
import { ToolCallBlock } from './ToolCallBlock'
import { FilePreviewModal } from '../atoms/FilePreviewModal'

interface Props {
  message: Message
  autoScroll: boolean
}

const roleClasses: Record<string, string> = {
  user:      'self-end bg-[var(--msg-user)]',
  assistant: 'self-start bg-[var(--msg-assistant)]',
  error:     'self-center bg-transparent text-[var(--danger)] text-center',
}

export function MessageBubble({ message, autoScroll }: Props) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [previewPath, setPreviewPath] = useState<string | null>(null)
  const [previewResult, setPreviewResult] = useState<unknown>(null)
  const bubbleRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (autoScroll && endRef.current) {
      endRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [message.content, message.toolPairs.length, autoScroll])

  const bubbleHeightPx = bubbleRef.current?.clientHeight ?? 400

  return (
    <>
      <div className="px-4 py-3">
        <div
          ref={bubbleRef}
          className={[
            'overflow-y-auto max-w-[75%] px-4 py-3 rounded-xl text-sm leading-relaxed',
            'whitespace-pre-wrap break-words font-mono font-light text-[var(--accent)]',
            'animate-[msgIn_0.25s_ease-out] relative',
            roleClasses[message.role] ?? '',
            message.role === 'assistant'
              ? isExpanded ? 'max-h-[800px]' : 'max-h-[250px]'
              : '',
          ].join(' ')}
        >
          {/* ToolCallBlocks above message text */}
          {message.role === 'assistant' && message.toolPairs.map((pair, i) => (
            <ToolCallBlock
              key={i}
              pair={pair}
              bubbleHeightPx={bubbleHeightPx}
              onFileClick={(path) => {
                setPreviewPath(path)
                setPreviewResult(pair.result)
              }}
            />
          ))}

          {message.content}

          {message.role === 'assistant' && (
            <button
              onClick={() => setIsExpanded(e => !e)}
              className="absolute top-2 right-2 text-sm text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors"
            >
              {isExpanded ? '▼' : '▲'}
            </button>
          )}

          <div ref={endRef} />
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
```

- [ ] **Step 4: Delete ToolCallPanel and clean up references**

```bash
rm frontend/src/components/atoms/ToolCallPanel.tsx
grep -rn "ToolCallPanel" frontend/src/
```

Remove every import and usage found.

- [ ] **Step 5: Run all frontend tests**

```bash
cd frontend && npx vitest run
```

All tests should pass. Fix any remaining TypeScript errors.

- [ ] **Step 6: Visual verification — start dev server**

```bash
./start.sh
```

Verify:
1. Agent messages show ToolCallBlocks above text, one per tool call
2. Streaming calls show pulsing indicator
3. Completed calls show `✓ tool_name · digest text ▼`
4. Clicking `▼` expands to HierarchyRenderer with 2-space indented tree
5. File paths in results are underlined; clicking opens FilePreviewModal
6. Modal is 60vw, letter-size, glows in theme accent color
7. Modal has 3 left-side tabs: document (syntax-highlighted), summary (metadata), JSON
8. Scrolling up suspends auto-scroll; "Jump to current ↓" button appears
9. Clicking button or scrolling to bottom re-engages auto-scroll

- [ ] **Step 7: Final commit**

```bash
git add frontend/src/components/molecules/MessageBubble.tsx \
        frontend/src/components/organisms/MessageList.tsx
git commit -m "feat: wire ToolCallBlocks into MessageBubble, add scroll tracking, remove ToolCallPanel"
```
