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

// ── www_search ───────────────────────────────────────────────────────────────

const wwwSearch: ToolAdapter = {
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

// ── Accounting helpers ────────────────────────────────────────

function fmtAmt(v: unknown): string {
  const n = typeof v === 'string' ? parseFloat(v) : asNum(v);
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function journalStanzaNodes(data: unknown): HierarchyNode[] {
  const d = asObj(data)
  const lines = asArr(d.lines)
  const id    = asStr(d.journal_entry_id !== undefined ? String(d.journal_entry_id) : d.id)
  const date  = asStr(d.date)
  const memo  = asStr(d.memo)
  const COL   = 28  // account name column width

  const nodes: HierarchyNode[] = [
    { label: `Entry #${id} · ${date}`, depth: 0, isFile: false },
    { label: memo, depth: 0, isFile: false },
  ]

  const COL_AMT = 12
  for (const l of lines) {
    const line    = asObj(l)
    const acct    = asStr(line.account)
    const debit   = parseFloat(asStr(line.debit, '0'))
    const credit  = parseFloat(asStr(line.credit, '0'))
    const isDebit = debit > 0
    const side    = isDebit ? 'Dr' : '  Cr'
    const amt     = fmtAmt(isDebit ? debit : credit)
    const padded  = acct.padEnd(COL).slice(0, COL)
    nodes.push({ label: `${padded}${side}  ${amt.padStart(COL_AMT)}`, depth: 1, isFile: false })
  }

  const total = fmtAmt(d.total_debits)
  const rule  = '─'.repeat(COL + 4 + COL_AMT)
  nodes.push({ label: rule, depth: 1, isFile: false })
  nodes.push({ label: `${'Total'.padEnd(COL)}    ${total.padStart(COL_AMT)}`, depth: 1, isFile: false })
  return nodes
}

// ── fa_tx_new ─────────────────────────────────────────────────

const faTxNew: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    return `Entry #${d.journal_entry_id} · ${asStr(d.memo)}`
  },
  toHierarchy(_p, data) { return journalStanzaNodes(data) },
}

// ── fa_tx_search ──────────────────────────────────────────────

const faTxSearch: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    return `${asNum(d.count)} journal entries`
  },
  toHierarchy(_p, data) {
    const d = asObj(data)
    const nodes: HierarchyNode[] = []
    for (const entry of asArr(d.entries)) {
      nodes.push(...journalStanzaNodes(entry))
      nodes.push({ label: '', depth: 0, isFile: false })
    }
    return nodes
  },
}

// ── fa_ls_accts ───────────────────────────────────────────────

const faLsAccts: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    return `${asNum(d.count)} accounts`
  },
  toHierarchy(_p, data) {
    const d = asObj(data)
    return asArr(d.accounts).map((a) => {
      const acct = asObj(a)
      const name = asStr(acct.name)
      const type = asStr(acct.account_type)
      const nb   = asStr(acct.normal_balance)
      return { label: `${name.padEnd(28).slice(0, 28)} ${type.padEnd(10)} ${nb}`, depth: 0, isFile: false }
    })
  },
}

// ── fa_acct_bal ───────────────────────────────────────────────

const faAcctBal: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    return `${asStr(d.account_name)}: ${fmtAmt(d.balance)}`
  },
  toHierarchy(_p, data) {
    const d = asObj(data)
    return [
      { label: asStr(d.account_name), depth: 0, isFile: false },
      { label: `Balance  ${fmtAmt(d.balance)}  (${asStr(d.normal_balance)} side)`, depth: 1, isFile: false },
    ]
  },
}

// ── fa_stmt ───────────────────────────────────────────────────

const faStmt: ToolAdapter = {
  summarize(_p, data) {
    const d = asObj(data)
    return `${asStr(d.statement_type)} · ${asStr(d.period_end ?? d.as_of_date)}`
  },
  toHierarchy(_p, data) {
    const d    = asObj(data)
    const rows = asArr(d.rows ?? d.lines ?? d.accounts)
    const nodes: HierarchyNode[] = [
      { label: `${asStr(d.statement_type)} as of ${asStr(d.period_end ?? d.as_of_date)}`, depth: 0, isFile: false },
    ]
    for (const row of rows) {
      const r   = asObj(row)
      const lbl = asStr(r.account ?? r.name ?? r.label)
      const amt = fmtAmt(r.amount ?? r.balance ?? r.value ?? 0)
      nodes.push({ label: `${lbl.padEnd(28).slice(0, 28)}  ${amt.padStart(12)}`, depth: 1, isFile: false })
    }
    if (d.net_income !== undefined || d.total !== undefined) {
      nodes.push({ label: '─'.repeat(42), depth: 1, isFile: false })
      const net = fmtAmt(d.net_income ?? d.total)
      const lbl = asStr(d.net_income !== undefined ? 'Net Income' : 'Total')
      nodes.push({ label: `${lbl.padEnd(28)}  ${net.padStart(12)}`, depth: 1, isFile: false })
    }
    return nodes
  },
}

// ── Registry ─────────────────────────────────────────────────────────────────

const ADAPTERS: Record<string, ToolAdapter> = {
  fs_tree:    fsTree,
  fs_ls_dir:  fsLsDir,
  fs_grep:    fsGrep,
  fs_find:    fsFind,
  www_search: wwwSearch,
  www_fetch:  wwwFetch,
  www_get:    wwwGet,
  fa_tx_new:    faTxNew,
  fa_tx_search: faTxSearch,
  fa_ls_accts:  faLsAccts,
  fa_acct_bal:  faAcctBal,
  fa_stmt:      faStmt,
}

export function getAdapter(toolName: string): ToolAdapter | null {
  return ADAPTERS[toolName] ?? null
}
