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
