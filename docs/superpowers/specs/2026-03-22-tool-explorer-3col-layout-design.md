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
- Response cached in ToolProvider state. Search filtering happens client-side against the cached index.
- Search input sends a query param to the server only if client-side filtering is insufficient (stretch goal — start with client-side).

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

The bottom bar is a single-row grid that mirrors the column template of the content area above.

### 2-Column Mode

```css
grid-template-columns: <sidebar-width> 1fr;
```

- **Left cell:** Empty placeholder. Same background as sidebar. Reserved for future controls (thinking toggle, settings).
- **Right cell:** InputBar component (unchanged from current).

### 3-Column Mode

```css
grid-template-columns: <sidebar-width> 1fr 22rem;
```

- **Left cell:** Same placeholder.
- **Center cell:** Empty placeholder. Reserved for future workspace-specific actions.
- **Right cell:** InputBar (narrower, text scaled down).

### Chat Collapsed

```css
grid-template-columns: <sidebar-width> 1fr 3rem;
```

- **Right cell:** Reopen chat button only.
- **Center cell:** Expands.

### Transitions

Bottom bar grid transitions match the content grid: `transition-[grid-template-columns] duration-300 ease-in-out`.

---

## 6. State Management

### New State (ChatPage level)

```typescript
// Whether the center workspace is open
workspaceOpen: boolean

// What the workspace is showing
workspaceView:
  | { type: 'category'; category: string }
  | { type: 'tool'; category: string; toolName: string }
  | null

// Whether the chat column is collapsed
chatCollapsed: boolean
```

### State Transitions

| Action | State Change |
|--------|-------------|
| Click category in sidebar | `workspaceOpen=true`, `workspaceView={type:'category', category}`, `chatCollapsed=false` |
| Click tool in search results | `workspaceOpen=true`, `workspaceView={type:'tool', category, toolName}`, `chatCollapsed=false` |
| Click "See more" on card | `workspaceView={type:'tool', category, toolName}` |
| Click category in breadcrumb | `workspaceView={type:'category', category}` |
| Click collapse chat | `chatCollapsed=true` |
| Click reopen chat button | `chatCollapsed=false` |
| Close workspace | `workspaceOpen=false`, `workspaceView=null`, `chatCollapsed=false` |

### ToolProvider Changes

- Add `toolIndex: ToolIndexEntry[]` state — the full list fetched from `tools.eric-merritt.com`.
- Add `searchTools(query: string, searchDescription: boolean): ToolIndexEntry[]` — client-side filter.
- Remove old `toggleTool` / `toggleCategory` methods (selection logic no longer needed).
- `ToolIndexEntry`: `{ name: string; description: string; category: string; params: Record<string, ToolParam> }`.

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
| `ChatPage.tsx` | Grid template supports 2 or 3 columns. New state: `workspaceOpen`, `workspaceView`, `chatCollapsed`. Workspace column + bottom bar segmentation. |
| `Sidebar.tsx` | Replace checkbox tool list with ToolSearch + category list. Click handlers open workspace instead of toggling selection. |
| `InputBar.tsx` | Accept a `compact` prop for narrow rendering (smaller text, smaller buttons). |
| `ToolProvider.tsx` | Fetch tool index from `tools.eric-merritt.com`. Expose `toolIndex` and `searchTools`. Remove toggle methods. |
| `useTools.ts` | Update hook to match new provider interface. |
| `api/tools.ts` | Add `fetchToolIndex()` function that hits `tools.eric-merritt.com`. Keep category inference logic. |

### Removed Components

| Component | Reason |
|-----------|--------|
| `ToolRow.tsx` | No longer needed — no checkbox rows |
| `ToolCategory.tsx` (molecule) | Replaced by sidebar category list + card grid |

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

## 9. Out of Scope (Future Iterations)

- Form submission and agent tool execution from workspace
- Response listener (HTTP server for structured tool results in workspace)
- Accounting interactive widget (JournalEntryForm in workspace)
- Bottom bar left cell content (thinking toggle, settings)
- Bottom bar center cell content (workspace-specific actions)
- Drag-to-resize column widths
- Tool favoriting or pinning
