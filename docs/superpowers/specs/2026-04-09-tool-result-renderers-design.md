# Tool Result Renderers — Design Spec
_2026-04-09_

## Overview

In-message structured rendering for filesystem and web tool results. Tool call blocks move inside the agent message bubble. Results are formatted client-side into a universal hierarchy view — raw JSON never re-enters LLM context. File paths are clickable and open a futuristic frosted-glass preview modal.

---

## Scope (Phase 1)

**Filesystem tools:** `fs_tree`, `fs_ls_dir`, `fs_grep`, `fs_find`
**Web tools:** `www_get`, `www_ddg`, `www_fetch`
**Deferred:** all other tool types (accounting, ecommerce, etc.) — adapters added later

---

## Component Architecture

### New components

```
atoms/
  HierarchyRenderer       — visual output: 2-space indentation, underlines, click handlers
  FilePreviewModal        — 3-tab modal overlay for file/result preview

molecules/
  ToolCallBlock           — single tool call with 3 display states

lib/
  toolAdapters.ts         — summarize() + toHierarchy() per tool, no React
```

### Modified components

```
organisms/MessageBubble   — renders ToolCallBlocks inline with text, fixed height + scroll
```

### New backend endpoint

```
GET /api/files/read?path=<encoded>
→ { content, language, size_bytes, truncated, lines_returned }
```

Language detected from file extension. Truncated at 500 lines. Images served via existing static file route or a new `/api/files/serve?path=`.

---

## HierarchyNode Type

```ts
interface HierarchyNode {
  label: string       // display text
  depth: number       // 0 = top level, 1 = 2 spaces, 2 = 4 spaces, etc.
  isFile: boolean     // applies underline + click handler
  href?: string       // absolute file path, used by FilePreviewModal
  isExternal?: boolean // true for web URLs — opens new tab instead of modal
}
```

Renderer applies `depth * 2` spaces of indentation. `isFile` nodes are underlined and open `FilePreviewModal` on click. `isExternal` nodes open in a new browser tab.

---

## toolAdapters.ts

Each tool exports two functions. Both receive the original call parameters AND the result data, since some summaries require inputs not echoed in the result (e.g. `www_ddg` query string):

```ts
summarize(params: unknown, data: unknown): string
toHierarchy(params: unknown, data: unknown): HierarchyNode[]
```

### Filesystem adapters

**`fs_tree` / `fs_ls_dir`**
- `summarize`: `"Directory: /src — 89 items"`
- `toHierarchy`: walks entries, depth from path segments, `isFile` on leaf nodes

**`fs_grep`**
- `summarize`: `"Found 14 matches for 'config' across 3 files"`
- `toHierarchy`:
  ```
  depth 0 — search summary line (not a node, part of digest)
  depth 0 — /src/config.py              (isFile, href)
  depth 1 — line 14: config = load_env()
  depth 1 — line 31: DEFAULT_CONFIG = { ... }
  depth 0 — /src/utils/helpers.py       (isFile, href)
  depth 1 — line 8: from config import settings
  ```

**`fs_find`**
- `summarize`: `"Found 8 files matching '*.py' in /src"`
- `toHierarchy`: flat list of file paths, depth 0, all `isFile`

### Web adapters

**`www_ddg`**
- `summarize`: `"Web search: 5 results"`
- `toHierarchy`:
  ```
  depth 0 — "config management best practices" — 5 results
  depth 0 — Stack Overflow | stackoverflow.com/...   (isExternal)
  depth 1 — How to manage config files in Python projects
  depth 0 — MDN Web Docs | developer.mozilla.org/...  (isExternal)
  depth 1 — Configuration patterns for modern web apps
  ```

**`www_fetch`**
- `summarize`: `"Fetched example.com — ref abc123, 45k chars"`
- `toHierarchy`: single node with title + ref, no children

**`www_get`**
- `summarize`: `"12 elements matching '.product-card'"`
- `toHierarchy`: flat list of results at depth 0, truncated at 20

---

## ToolCallBlock States

### 1. Streaming
```
⟳ fs_grep  searching...
```
Pulsing indicator, tool name, no result. Matches existing streaming aesthetic.

### 2. Completed / digest (~1 inch tall, default)
```
✓ fs_grep  ·  Found 14 matches for 'config' across 3 files        ▼
```
Single line. Done badge, tool name, `summarize()` output, expand chevron (▼). Uses existing chevron pattern from MessageBubble.

### 3. Expanded (60% of the agent bubble's fixed height)
```
✓ fs_grep  ·  Found 14 matches for 'config' across 3 files        ▲
──────────────────────────────────────────────────────────────────
/src/config.py
  line 14: config = load_env()
  line 31: DEFAULT_CONFIG = { ... }
/src/utils/helpers.py
  line 8: from config import settings
```
`HierarchyRenderer` output, scrollable. File/URL nodes underlined and clickable.

---

## FilePreviewModal

### Layout
- **Width:** 60% viewport width
- **Aspect ratio:** letter-size proportion (~8.5:11)
- **Position:** centered overlay
- **Header:** file path or result title

### Two-zone layout
```
┌────────────────────────────────────────────┐
│ /src/config.py                    [✕]      │
├──┬─────────────────────────────────────────┤
│  │                                         │
│🖹│         main content area               │
│  │         (switches per active tab)       │
│📋│                                         │
│  │                                         │
│{}│                                         │
│  │                                         │
└──┴─────────────────────────────────────────┘
```

**Left strip — 3 vertical icon tabs:**
1. **Doc / photo** — file content (default). Syntax-highlighted code for text files, `<img>` for images, "Preview unavailable" for unknown/binary.
2. **Summary** — tool call digest + file metadata (path, language, size, modified time, line count).
3. **JSON** — raw `tool_result` data payload, pretty-printed, monospace.

### File type handling (Phase 1)

| Type | Detection | Render |
|---|---|---|
| Code / text | Extension (`.py`, `.ts`, `.md`, `.json`, etc.) | Syntax-highlighted, line numbers, monospace |
| Image | `.png`, `.jpg`, `.gif`, `.svg`, `.webp` | `<img>` via `/api/files/serve?path=` |
| Unknown / binary | Fallback | "Preview unavailable" message |

Phase 2: PDF via `pymupdf` text extraction on the backend.

### Visual design
- **Base:** existing glass theme CSS custom properties
- **Accent:** theme accent color pushed to high saturation and luminosity
- **Border:** glowing 1–2px border in amplified accent color (`box-shadow` glow outward)
- **Background:** `backdrop-filter: blur(24px)` + accent color at ~8% opacity tint
- **Effect:** reads as frosted neon glass — hot pink on purple theme, shifts per theme via CSS variables
- **Goal:** glows, could be radioactive, definitely futuristic

---

## MessageBubble Changes

- `ToolCallBlock` components render inline above the text response, one per tool call
- Existing fixed height + scroll remains unchanged
- `ToolCallPanel` (current collapsible aggregate) removed and replaced by per-call `ToolCallBlock`s

---

## Backend: `/api/files/read`

```
GET /api/files/read?path=/absolute/path/to/file
→ 200 { content, language, size_bytes, lines_returned, truncated }
→ 403 if path escapes allowed roots
→ 404 if not found
```

Language detection: extension map in Python (`{'.py': 'python', '.ts': 'typescript', ...}`). Truncated at 500 lines, `truncated: true` flag returned if so. Path validation prevents directory traversal.

---

## Scroll Behavior

Auto-scroll follows the stream by default. User scrolling up cancels it — stream continues growing out of view. Re-engages when the user either scrolls back to the bottom naturally or clicks a **"Jump to current"** button that appears while auto-scroll is suspended. Button disappears once re-engaged.

Implementation: track a `isUserScrolling` flag. Set it `true` on manual scroll-up (detected via `onScroll` comparing `scrollTop + clientHeight < scrollHeight - threshold`). Set it `false` when user reaches the bottom or clicks the button. Auto-scroll only fires when `isUserScrolling` is `false`.

---

## What's Not In Scope

- Workspace file explorer (separate spec)
- PDF rendering (Phase 2)
- Adapters for non-filesystem/web tools (added incrementally)
- Editing files from the modal
- Search within modal content
