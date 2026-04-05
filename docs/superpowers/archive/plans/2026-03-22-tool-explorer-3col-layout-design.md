# Tool Explorer & 3-Column Layout Design

**Date:** 2026-03-22
**Goal:** Replace the empty sidebar with a tool explorer that searches the MCP tool registry, and introduce a 3-column layout with a center workspace for browsing tool categories, viewing tool documentation, and (future) interactive tool forms.

---

## 1. Layout States

### 2-Column (default — current behavior)

```
[Sidebar 6rem/22rem] [Chat 1fr           ]
[BottomL            ] [InputBar           ]
```

- Sidebar expand/collapse behavior unchanged (chevron toggle, 6rem ↔ 22rem, 300ms transition).
- Bottom bar splits at the sidebar boundary. Left cell is a placeholder (future: thinking toggle, settings icons). Right cell is the existing InputBar.

### 3-Column (workspace open)

```
[Sidebar 6rem/22rem] [Workspace 1fr] [Chat 22rem       ]
[BottomL            ] [BottomC      ] [InputBar (narrow) ]
```

- Triggered when the user clicks a tool category or individual tool in the sidebar explorer.
- Chat column shrinks to `22rem` with reduced text size.
- Center workspace column takes `1fr`.
- Bottom bar segments into 3 cells matching column widths above.
- All column transitions use `transition-[grid-template-columns] duration-300 ease-in-out`.

### 3-Column with chat collapsed

```
[Sidebar 6rem/22rem] [Workspace 1fr                     ]
[BottomL            ] [BottomC         ] [Reopen button  ]
```

- Chat column width becomes `0`. InputBar disappears.
- The right bottom cell renders a single styled button (chat bubble icon) that reopens the chat.
- Center workspace + bottom-center expand to fill the freed space.
- The reopen button occupies a minimal fixed-width cell (e.g., `3rem`).

---

## 2. Tool Explorer Sidebar

Content replaces the old checkbox-based tool selector. Spatial dimensions unchanged.

### Search

- Text input at the top of the sidebar content area.
- Queries `https://tools.eric-merritt.com` on input (debounced, ~300ms).
- Two small checkboxes below the input: **Name** (checked by default), **Description** (unchecked by default). Controls which fields are matched.
- Matches returned as a filtered list below the search bar.

### Results List (search active)

- Each result: tool name (monospace, accent color, truncated) + first line of description (muted, smaller).
- Click a result → opens tool detail view in center workspace (triggers 3-column layout).

### Category List (search empty)

- Collapsible category groups: Filesystem, Web, Ecommerce, Accounting, Other.
- Same category inference rules as current `api/tools.ts` `CATEGORY_RULES`.
- No checkboxes — categories are purely navigational.
- Click a category name → opens category card grid in center workspace (triggers 3-column layout).
- Expand a category → shows tool names inline (click any tool → tool detail view in workspace).

### Data Source

- Tool index fetched from `https://tools.eric-merritt.com` at startup (same endpoint the backend pre-pass uses).
- **CORS:** The external endpoint must serve `Access-Control-Allow-Origin` for the frontend origin. If CORS headers are not present, proxy the request through the Flask backend at `GET /api/tools/index` to avoid browser restrictions.
- Response cached in ToolProvider state. Search filtering happens client-side against the cached index.
- Search input sends a query param to the server only if client-side filtering is insufficient (stretch goal — start with client-side).

### Loading / Error / Empty States

- **Loading:** Sidebar shows a small centered spinner or "Loading tools..." text while the index is being fetched.
- **Error:** If the fetch fails, show a retry-able error message in the sidebar: "Failed to load tools" with a "Retry" link.
- **Empty:** If the index returns no tools, show "No tools available" in muted text.

---

## 3. Center Workspace

### Category Card Grid

Displayed when a category is clicked in the sidebar.

- Responsive CSS grid: `grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr))`.
- Each card:
  - Tool name as heading (monospace, small).
  - First line of description (muted, smaller text).
  - "See more" link (accent color).
- Card styling: glass background (`var(--glass-bg)`), accent border on hover, rounded corners.
- Breadcrumb at top: category name. No back arrow needed — clicking another category or closing the workspace navigates away.

### Tool Detail View

Displayed when "See more" is clicked on a card, or a tool is clicked directly from search results.

- **Breadcrumb:** `Category > Tool Name` — category name is a link back to the card grid.
- **Tool name** as heading.
- **Full description** from docstring (rendered as preformatted/monospace text, preserving the WHEN TO USE / WHEN NOT TO USE / Args / Output format structure).
- **Parameter table:**
  - Columns: Name, Type, Required, Description.
  - Data sourced from tool schema (`params` object).
  - Styled as a bordered table with the glass/accent aesthetic.
- **Doc ↔ Form toggle:** A toggle/switch on the parameter table header. When switched to form mode:
  - Each table row becomes an input field (text input, number input, or checkbox depending on type).
  - Labels match the parameter names from the table.
  - A "Submit" button appears below the form.
  - Form submission is **out of scope** for this iteration — the toggle and form rendering are in scope. The submit button is visible but disabled with a "Coming soon" tooltip.

### Text Sizing

- All workspace text one step smaller than chat defaults to fit the column width.
- Tool names: `text-sm` monospace.
- Descriptions: `text-xs`.
- Table cells: `text-xs`.

---

## 4. Chat Column (Minimized State)

When the workspace is open, the chat column at `22rem`:

- **Messages:** `text-xs` on message content, `text-[10px]` on timestamps and metadata.
- **ToolCallPanel:** Same content, smaller text.
- **InputBar:** Renders inside the narrow column. Input text `text-xs`. Send/Clear buttons shrink.
- **Collapse button:** Small chevron or X icon in the top-right of the chat area. Clicking it collapses the chat column to `0`.

When collapsed:
- Chat column width is `0`, content hidden (`overflow: hidden`).
- Bottom bar right cell shows a styled button (chat bubble icon + "Chat" label or just icon) that reopens to `22rem`.
- Reopen button styling: accent background, rounded, centered in its cell.

When reopened:
- Animates back to `22rem` with the same grid transition.

### Full-width Chat Restoration

- Closing the workspace (e.g., clicking an X/close button on the workspace, or a "Close" action in the breadcrumb area) returns to the 2-column layout.
- Chat expands back to `1fr`.

---

## 5. Bottom Bar

### DOM Structure

The current ChatPage uses a single CSS grid with `grid-rows-[1fr_auto]` where InputBar spans all columns via `col-span-*`. This won't work for independently segmented bottom bar cells. Instead:

**New structure:** A flex column (`flex flex-col h-screen`) containing two grids stacked vertically:

1. **Content grid** (`flex-1`): Sidebar + Chat (2-col) or Sidebar + Workspace + Chat (3-col).
2. **Bottom bar grid** (`flex-none`): Mirrors the content grid's column template.

Both grids share the same `gridTemplateColumns` value via a CSS custom property or a shared variable in the component. This keeps columns aligned without subgrid (which has limited browser support).

```tsx
const cols = workspaceOpen
  ? chatCollapsed
    ? `${sidebarWidth} 1fr 3rem`
    : `${sidebarWidth} 1fr 22rem`
  : `${sidebarWidth} 1fr`;

<div className="flex flex-col h-screen">
  <TopBar />
  <div className="flex-1 grid" style={{ gridTemplateColumns: cols }}>
    {/* content cells */}
  </div>
  <div className="grid" style={{ gridTemplateColumns: cols }}>
    {/* bottom bar cells */}
  </div>
</div>
```

### 2-Column Mode

- **Left cell:** Empty placeholder. Same background as sidebar. Reserved for future controls (thinking toggle, settings).
- **Right cell:** InputBar component (unchanged from current).

### 3-Column Mode

- **Left cell:** Same placeholder.
- **Center cell:** Empty placeholder. Reserved for future workspace-specific actions.
- **Right cell:** InputBar (narrower, text scaled down).

### Chat Collapsed

- **Right cell:** ChatReopenButton only (in a `3rem`-wide cell).
- **Center cell:** Expands to fill freed space.

### Transitions

Both grids animate together: `transition-[grid-template-columns] duration-300 ease-in-out`.

---

## 6. State Management

### New State (ChatPage level)

```typescript
// What the workspace is showing — null means workspace is closed (2-column mode)
workspaceView:
  | { type: 'category'; category: string }
  | { type: 'tool'; category: string; toolName: string }
  | null

// Derived: const workspaceOpen = workspaceView !== null

// Whether the chat column is collapsed (only meaningful when workspace is open)
chatCollapsed: boolean
```

**Note:** `workspaceOpen` is derived from `workspaceView !== null` — not stored as separate state. This prevents impossible states like `workspaceOpen=true, workspaceView=null`.

### State Transitions

| Action | State Change |
|--------|-------------|
| Click category in sidebar | `workspaceView={type:'category', category}`, `chatCollapsed=false` |
| Click tool in search results | `workspaceView={type:'tool', category, toolName}`, `chatCollapsed=false` |
| Click "See more" on card | `workspaceView={type:'tool', category, toolName}` |
| Click category in breadcrumb | `workspaceView={type:'category', category}` |
| Click collapse chat | `chatCollapsed=true` |
| Click reopen chat button | `chatCollapsed=false` |
| Close workspace | `workspaceView=null`, `chatCollapsed=false` |
| Escape key | `workspaceView=null`, `chatCollapsed=false` (returns to 2-column) |

### ToolProvider Changes

- Add `toolIndex: ToolIndexEntry[]` state — the full list fetched from `tools.eric-merritt.com`.
- Add `searchTools(query: string, searchDescription: boolean): ToolIndexEntry[]` — client-side filter.
- Remove old `toggleTool` / `toggleCategory` methods and `selected` state. The backend pre-pass now handles dynamic tool selection per-turn — the frontend no longer needs to track or send tool selection state. The `POST /api/tools/select` and `POST /api/tools/deselect` endpoints are vestigial and unused.
- `ToolIndexEntry` replaces the existing `Tool` type in `atoms/tool.ts`: `{ name: string; description: string; category: string; params: Record<string, ToolParam> }`. The `selected` boolean is dropped. `ToolCategory` type is kept but its `allSelected`/`someSelected`/`selectedCount` computed fields are removed — it becomes `{ name: string; tools: ToolIndexEntry[]; count: number }`. The `buildCategory` factory is updated accordingly.
- `CATEGORY_RULES` and category inference logic remain in `api/tools.ts` and are reused to assign `category` to each `ToolIndexEntry`.

---

## 7. New & Modified Components

### New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `ToolSearch` | `atoms/ToolSearch.tsx` | Search input + name/description checkboxes |
| `ToolSearchResults` | `molecules/ToolSearchResults.tsx` | Filtered results list below search |
| `CategoryCardGrid` | `organisms/CategoryCardGrid.tsx` | Card grid for a tool category |
| `ToolDetailView` | `organisms/ToolDetailView.tsx` | Full tool doc + parameter table + form toggle |
| `ToolCard` | `molecules/ToolCard.tsx` | Individual card in the grid |
| `ParamTable` | `molecules/ParamTable.tsx` | Parameter table with doc/form toggle |
| `Workspace` | `organisms/Workspace.tsx` | Container that routes between CategoryCardGrid and ToolDetailView based on workspaceView state |
| `ChatReopenButton` | `atoms/ChatReopenButton.tsx` | Styled button to reopen collapsed chat |

### Modified Components

| Component | Changes |
|-----------|---------|
| `ChatPage.tsx` | Restructure from single grid to flex column with two grids (content + bottom bar). New state: `workspaceView`, `chatCollapsed`. Shared `gridTemplateColumns` variable. Workspace column rendering. |
| `Sidebar.tsx` | Full content rewrite: remove ToolCategory/ToolRow imports and all checkbox/toggle logic. Replace with ToolSearch + navigational category list. Click handlers call workspace state setters (passed as props or via context). |
| `InputBar.tsx` | Accept a `compact` prop for narrow rendering (smaller text, smaller buttons). Remove `ToolChip` rendering and `selected`/`toggleTool` usage from `useTools()` — tool selection is no longer a frontend concern. |
| `ToolProvider.tsx` | Fetch tool index from `tools.eric-merritt.com`. Expose `toolIndex`, `searchTools`, `categories`, `loading`, `error`. Remove `toggleTool`, `toggleCategory`, `selected` state entirely. |
| `useTools.ts` | Update hook to match new provider interface (drop `selected`, `toggleTool`, `toggleCategory`; add `toolIndex`, `searchTools`, `categories`, `loading`, `error`). |
| `api/tools.ts` | Add `fetchToolIndex()` function that hits `tools.eric-merritt.com` (or `/api/tools/index` proxy). Keep `CATEGORY_RULES` and `inferCategory()`. Remove `selectTool()`/`deselectTool()` fetch wrappers. |
| `atoms/tool.ts` | Replace `Tool` type with `ToolIndexEntry` (drop `selected` field). Simplify `ToolCategory` to `{ name: string; tools: ToolIndexEntry[]; count: number }`. Update `buildCategory` factory. |

### Removed Components

| Component | Reason |
|-----------|--------|
| `ToolRow.tsx` | No longer needed — no checkbox rows |
| `ToolCategory.tsx` (molecule) | Replaced by sidebar category list + card grid |
| `ToolChip.tsx` (molecule) | Tool selection badges no longer rendered in InputBar |

---

## 8. API Integration

### Tool Index Endpoint

```
GET https://tools.eric-merritt.com/
```

Response format (based on what the backend pre-pass already uses): a JSON object mapping tool names to their metadata. The frontend fetches this once on mount and caches it in ToolProvider.

### Search Strategy

1. **Client-side filtering** against the cached tool index.
2. Filter by `name.includes(query)` (when Name checkbox checked) and/or `description.includes(query)` (when Description checkbox checked).
3. Case-insensitive matching.
4. Results sorted: exact prefix matches first, then substring matches.

---

## 9. Keyboard & Viewport

- **Escape** closes the workspace and returns to 2-column layout (state transition in table above).
- **Minimum viewport:** The 3-column layout requires ~1280px to be usable (22rem sidebar + workspace + 22rem chat). On viewports narrower than 1280px, the workspace should not open — tool clicks navigate to the tool detail as a full-width overlay instead. Implementation of the narrow-viewport fallback is a stretch goal for this iteration.

---

## 10. Out of Scope (Future Iterations)

- Form submission and agent tool execution from workspace
- Response listener (HTTP server for structured tool results in workspace)
- Accounting interactive widget (JournalEntryForm in workspace)
- Bottom bar left cell content (thinking toggle, settings)
- Bottom bar center cell content (workspace-specific actions)
- Drag-to-resize column widths
- Tool favoriting or pinning
- Full keyboard navigation (arrow keys in search results, tab order)
- WorkspaceContext/provider (if prop drilling becomes unwieldy during implementation)
