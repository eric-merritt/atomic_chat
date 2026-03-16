# React + Tailwind Frontend Refactor

**Date:** 2026-03-16
**Status:** Approved
**Scope:** Replace inline HTML/JS/CSS in Flask with a React SPA frontend

---

## 1. Architecture

### Two processes in development, one in production

**Development:**
- `vite dev` on port 5173 with HMR, proxies `/api/*` and `/static/*` to Flask on port 5000
- `python main.py --serve` on port 5000 as a headless API server

**Production:**
- `vite build` outputs to `frontend/dist/`
- `python main.py --serve` serves both the API and the static bundle
- Existing nginx reverse proxy config unchanged

### Flask backend changes

- Delete `INDEX_HTML` template string (~580 lines of inline HTML/JS/CSS)
- Delete `GET /` route (template render) and `GET /main.css` route
- Add catch-all route serving `frontend/dist/index.html` for client-side routing
- All `/api/*` routes, WebSocket handler, middleware, LangGraph, ChromaDB RAG — untouched

### Adapter pattern

The frontend API layer uses a strict adapter pattern: one file per endpoint that transforms raw Flask JSON into typed atoms. When the backend is eventually refactored (Postgres, SQLAlchemy, proper response schemas), only the adapter changes — not the components.

---

## 2. Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Build tool | Vite | SPA bundler, no SSR overhead, fast HMR |
| Framework | React 19 | Component model, ecosystem |
| Language | TypeScript | Typed atoms, self-documenting contracts |
| Styling | Tailwind CSS | Inline utility classes, matches inline-HTML simplicity |
| Routing | React Router | Multi-page support for future routes (model query page, settings, ad placements) |
| State | React built-ins | useState + useContext + custom hooks, no external store |
| Streaming | Custom `useStream` hook | NDJSON over fetch ReadableStream |
| WebSocket | Native WebSocket API | Custom `useWebSocket` hook for remote execution mode |

**Not included:** Next.js (SSR unnecessary, API routes conflict with Flask), Redux (overkill), Socket.IO (unnecessary weight), React Query (few endpoints).

---

## 3. Project Structure

```
agentic_w_langchain_ollama/
├── frontend/
│   ├── src/
│   │   ├── atoms/           # Data types — the fundamental units
│   │   │   ├── model.ts
│   │   │   ├── tool.ts
│   │   │   ├── message.ts
│   │   │   ├── theme.ts
│   │   │   ├── stream.ts
│   │   │   ├── agent.ts
│   │   │   └── api.ts
│   │   ├── components/
│   │   │   ├── atoms/       # Primitive UI components
│   │   │   │   ├── Button.tsx
│   │   │   │   ├── Input.tsx
│   │   │   │   ├── Select.tsx
│   │   │   │   ├── Badge.tsx
│   │   │   │   ├── Icon.tsx
│   │   │   │   ├── Checkbox.tsx
│   │   │   │   ├── StatusText.tsx
│   │   │   │   └── Dot.tsx
│   │   │   ├── molecules/   # Composed atoms with minimal logic
│   │   │   │   ├── ChatInput.tsx
│   │   │   │   ├── ToolChip.tsx
│   │   │   │   ├── CategoryHeader.tsx
│   │   │   │   ├── ToolRow.tsx
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   ├── ImageThumbnail.tsx
│   │   │   │   ├── ModelSelect.tsx
│   │   │   │   └── ThinkingIndicator.tsx
│   │   │   └── organisms/   # Business logic, API-aware
│   │   │       ├── TopBar.tsx
│   │   │       ├── Sidebar.tsx
│   │   │       ├── MessageList.tsx
│   │   │       ├── InputBar.tsx
│   │   │       └── Lightbox.tsx
│   │   ├── hooks/
│   │   │   ├── useModels.ts
│   │   │   ├── useTools.ts
│   │   │   ├── useChat.ts
│   │   │   ├── useTheme.ts
│   │   │   ├── useStream.ts
│   │   │   └── useWebSocket.ts
│   │   ├── api/             # Adapter layer — Flask JSON → typed atoms
│   │   │   ├── models.ts
│   │   │   ├── tools.ts
│   │   │   ├── chat.ts
│   │   │   ├── history.ts
│   │   │   └── system.ts
│   │   ├── pages/
│   │   │   └── ChatPage.tsx
│   │   ├── providers/
│   │   │   ├── ThemeProvider.tsx
│   │   │   ├── ModelProvider.tsx
│   │   │   ├── ToolProvider.tsx
│   │   │   ├── ChatProvider.tsx
│   │   │   └── WebSocketProvider.tsx
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css        # Tailwind directives + theme CSS variables
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
├── main.py                   # Flask API (INDEX_HTML deleted)
├── main.css                  # Deleted after port
├── config.py
├── tools/
├── agents/
└── ...
```

---

## 4. Atomic Type System

Every domain concept is a typed atom. No `any`, no inline shapes.

### `atoms/model.ts`

```typescript
interface Model {
  devTeam: string | null;  // "huihui_ai" — null for official Ollama library models
  name: string;            // "qwen2.5-coder-abliterate"
  numParams: string;       // "14b"
  available: boolean;      // true if present in local Ollama instance

  // Rich metadata — nullable until Postgres backend provides it.
  format: string | null;          // "HF" | "GGUF" | "original"
  maker: string | null;           // "Alibaba/Qwen"
  year: number | null;
  description: string | null;
  goodAt: string[] | null;
  notSoGoodAt: string[] | null;
  idealUseCases: string[] | null;
  contextWindow: number | null;
}

// modelId is NOT stored — it's derived.
// Ollama expects "devTeam/name:params" or "name:params" format.
function modelId(m: Model): string {
  const base = m.devTeam ? `${m.devTeam}/${m.name}` : m.name;
  return `${base}:${m.numParams}`;
}

// Examples:
//   modelId({ devTeam: "huihui_ai", name: "qwen2.5-coder-abliterate", numParams: "14b" })
//   → "huihui_ai/qwen2.5-coder-abliterate:14b"
//
//   modelId({ devTeam: null, name: "llama3.1", numParams: "8b" })
//   → "llama3.1:8b"
```

The current `GET /api/models` endpoint returns `{models: string[], current: string}` — strings like `"huihui_ai/qwen2.5-coder-abliterate:14b"` or `"llama3.1:8b"`. The adapter parses these: splits on `/` for optional `devTeam`, then on `:` for `name` and `numParams`. All metadata fields null. This is an intentional gap: the full `Model` shape exists so that when the Postgres backend arrives, the adapter is the only thing that changes.

### `atoms/tool.ts`

```typescript
interface ToolParam {
  type: string;
  description: string;
  required: boolean;
  default?: unknown;
}

interface Tool {
  name: string;
  description: string;
  params: Record<string, ToolParam>;
  category: string;
  selected: boolean;
}

interface ToolCategory {
  name: string;
  tools: Tool[];
  // Derived client-side from tools[].selected — not from backend response.
  // Backend sends all_selected/some_selected/count/selected_count but
  // the frontend computes these via helper functions to stay decoupled.
  readonly allSelected: boolean;
  readonly someSelected: boolean;
  readonly count: number;
  readonly selectedCount: number;
}

// Factory function computes derived fields from tools[].selected:
// buildCategory(name, tools) → ToolCategory
```

### `atoms/message.ts`

```typescript
type MessageRole = "user" | "assistant" | "error";

interface ImageAttachment {
  src: string;
  filename: string;
  sizeKb: number;
}

interface ToolCallInfo {
  id?: string;      // present in WebSocket protocol for request-response correlation
  tool: string;
  input: string;    // stringified args — streaming sends string, WebSocket sends object
  params?: Record<string, unknown>;  // parsed args — WebSocket wire format uses this
}

// The useWebSocket hook normalizes params→input (JSON.stringify) so downstream
// components always read ToolCallInfo.input as a string. params is preserved
// for components that need structured access (e.g. tool result rendering).

interface Message {
  id: string;
  role: MessageRole;
  content: string;
  images: ImageAttachment[];
  toolCalls: ToolCallInfo[];
  timestamp: number;
}
```

### `atoms/theme.ts`

```typescript
type ThemeMode = "dark" | "light";

interface Theme {
  id: string;          // "obsidian" | "carbon" | "amethyst" | "frost" | "sand" | "blossom"
  label: string;
  mode: ThemeMode;
}
```

### `atoms/stream.ts`

The backend emits flat NDJSON objects discriminated by top-level key (not a `type` field):

```json
{"token": "text"}
{"tool_call": {"tool": "name", "input": "args"}}
{"tool_result": {"tool": "name", "output": "result"}}
{"image": {"src": "/static/images/...", "filename": "...", "size_kb": 0}}
{"error": "message"}
```

The `useStream` hook parses the raw wire format and normalizes it into a typed discriminated union:

```typescript
// Wire format — what the backend sends (snake_case, key-based discrimination)
type RawStreamLine =
  | { token: string }
  | { tool_call: { tool: string; input: string } }
  | { tool_result: { tool: string; output: string } }
  | { image: { src: string; filename: string; size_kb: number } }
  | { error: string };

// Normalized frontend type — what hooks and components consume
type StreamEvent =
  | { type: "token"; token: string }
  | { type: "tool_call"; tool: string; input: string }
  | { type: "tool_result"; tool: string; output: string }
  | { type: "image"; src: string; filename: string; sizeKb: number }
  | { type: "error"; message: string };

// parseStreamLine() in useStream detects the top-level key and maps to StreamEvent
```

### `atoms/agent.ts`

```typescript
type LoopStepKind = "inference" | "summarization" | "definition" | "execution";

interface LoopStep {
  kind: LoopStepKind;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  result?: string;
}

interface Plan {
  id: string;
  steps: LoopStep[];
  createdAt: number;
}
```

### `atoms/api.ts`

```typescript
interface ApiResponse<T> {
  data: T;
  error?: string;
}
```

---

## 5. Hooks & State Management

Each hook owns one domain. No global store. Components subscribe only to what they need.

### Context hierarchy

Providers are nested (not siblings) so inner providers can consume outer ones:

```
ThemeProvider           → useTheme()
  └── ModelProvider     → useModels()
    └── ToolProvider    → useTools()
      └── ChatProvider  → useChat()  — reads ModelProvider + ToolProvider
        └── WebSocketProvider → useWebSocket() (conditional)
```

`ChatProvider` consumes `useModels()` and `useTools()` from its ancestor providers. When the user selects a new model (which resets history on the backend), `ChatProvider` listens and clears local messages. This nesting order ensures each provider can access the contexts it depends on.

### `useModels()`

- Fetches `GET /api/models` on mount
- Tracks current selection
- Exposes `selectModel(model: Model)` → `POST /api/models` (adapter calls `modelId(model)` to build the API payload)
- Returns `{ models: Model[], current: Model | null, selectModel, loading }`

### `useTools()`

- Fetches `GET /api/tools` on mount
- Tracks selected set
- Exposes `toggleTool(name)` → `POST /api/tools/toggle`
- Exposes `toggleCategory(name)` → `POST /api/tools/toggle_category`
- Returns `{ categories: ToolCategory[], selected: string[], toggleTool, toggleCategory }`

### `useChat()`

- Manages message list (array of `Message` atoms)
- `sendMessage(text)` → creates `useStream` instance → `POST /api/chat/stream`
- `cancelStream()` → `POST /api/chat/cancel`
- `clearHistory()` → `DELETE /api/history` + clears local messages
- Returns `{ messages: Message[], sendMessage, cancelStream, clearHistory, streaming: boolean }`

### `useStream()`

- Internal hook consumed by `useChat`
- Fetch + ReadableStream + NDJSON line parser
- Parses each line into typed `StreamEvent` discriminated union
- Calls event handlers: `onToken`, `onToolCall`, `onToolResult`, `onImage`, `onError`

### `useTheme()`

- Reads from localStorage on mount
- Sets `data-theme` attribute on `<html>`
- Exposes `setTheme(id: string)`
- Returns `{ theme: Theme, setTheme, themes: Theme[] }`

### `useWebSocket()`

- Native WebSocket connection to `/api/chat/ws`
- Only active when execution mode is remote
- First message includes auth: `{api_key: string, message: string}`
- Receives `{tool_call: {id, tool, params}}` — `id` correlates request/response
- Sends `{tool_result: {id, output}}` back
- Stream ends on `{done: true}`
- Returns `{ connected: boolean, sendToolResult(id: string, output: string) }`

---

## 6. Component Details

### UI Atoms (components/atoms/)

All purely presentational. Accept props, render markup, emit callbacks. Zero API calls, zero context consumption. Styled with Tailwind utility classes.

`Button` accepts `variant: "primary" | "ghost" | "danger"`, maps to Tailwind classes. `Checkbox` accepts `indeterminate: boolean` via ref. `Icon` wraps inline SVGs by name.

### Molecules (components/molecules/)

`ModelSelect` — consumes `useModels()`, renders `Select` atom populated with `Model` atoms. Self-contained: fetches, selects, displays status.

`ChatInput` — composes `Input` + `Button`(send) + `Button`(stop) + `Button`(clear). Receives `onSend`, `onCancel`, `onClear`, `streaming` as props.

`ToolChip` — renders `Badge` with selected count. Hover shows popup listing selected `Tool` atoms with remove buttons.

`ThinkingIndicator` — `Dot` x3 + `StatusText` (label) + timer + preview text. Receives current `StreamEvent` to update label ("working" → "calling tool" → "got result").

`MessageBubble` — renders a `Message` atom. Parses markdown images from content. Role determines alignment and color.

### Organisms (components/organisms/)

`TopBar` — renders `ModelSelect` molecule + `StatusText` + theme `Select`. Fixed height.

`Sidebar` — renders list of `CategoryHeader` + `ToolRow` molecules. Consumes `useTools()`. Toggle button triggers grid animation (see Section 7).

`MessageList` — scrollable container, maps `messages` from `useChat()` to `MessageBubble` and `ImageThumbnail` molecules. Auto-scrolls on new messages. Renders `ThinkingIndicator` when streaming.

`InputBar` — renders `ToolChip` + `ChatInput`. Consumes `useChat()` for `sendMessage` and `streaming` state.

`Lightbox` — fixed overlay. Receives `src`, `caption`, `onClose`. Rendered conditionally via state in `ChatPage`.

### Error boundaries

Each organism is wrapped in a React error boundary. A streaming failure in `MessageList` should not crash the `Sidebar` or `InputBar`. The error boundary renders a minimal fallback with a retry button. `ChatPage` itself has a top-level boundary as a last resort.

### Pages

`ChatPage` — composes all organisms in a CSS grid layout. Manages lightbox state. This is the current app as a single route.

Future pages (`/models/:name`, `/settings`) added via React Router without touching existing components.

---

## 7. Layout & Grid System

### Grid structure

The `.main` container uses CSS grid with implicit placement (no explicit `grid-area` on children):

```
grid-template-columns: [sidebar-col] [content-col]
grid-template-rows: [content-row] [input-row]
```

TopBar sits outside the grid (fixed top). Sidebar, MessageList, and InputBar are grid children placed by document order, not explicit grid-area assignments.

### Sidebar animation

`grid-area` is not animatable (discrete property). Instead, animate `grid-template-columns` on the grid container:

- **Collapsed:** `grid-template-columns: 4.5rem 1fr`
- **Expanded:** `grid-template-columns: 35rem 1fr`

CSS handles the interpolation. Tailwind: `transition-[grid-template-columns] duration-300 ease-in-out`.

The sidebar toggle function sets `grid-template-columns` on the grid container. Children don't move — the grid reshapes around them.

### Theme system

The 6 themes (obsidian, carbon, amethyst, frost, sand, blossom) are preserved as CSS custom properties on `[data-theme="..."]` selectors. These live in `index.css` alongside Tailwind directives. Components reference them via Tailwind's arbitrary values (`text-[var(--text)]`, `bg-[var(--glass-bg)]`) or via `tailwind.config.ts` theme extension.

### Particle canvas

The particle animation system is ported as a standalone React component with a `useEffect` + canvas ref. Theme-aware color palettes update via MutationObserver on `data-theme` (same pattern as current implementation).

---

## 8. API Adapter Layer

One file per endpoint domain. Each adapter:
1. Makes the fetch call
2. Validates the response shape
3. Transforms raw JSON into typed atoms
4. Returns `ApiResponse<T>`

```
src/api/
├── models.ts    # fetchModels() → Model[], selectModel(name) → Model
├── tools.ts     # fetchTools() → ToolCategory[], toggleTool(name), toggleCategory(name)
├── chat.ts      # streamChat(message) → ReadableStream, cancelChat()
├── history.ts   # fetchHistory() → Message[], clearHistory()
└── system.ts    # fetchSystemPrompt() → string, setSystemPrompt(prompt) → string
```

**Adapter gap: `GET /api/history`** returns `{history: [{role, content}]}` — flat objects without `id`, `images`, `toolCalls`, or `timestamp`. The `history.ts` adapter synthesizes these: generates UUIDs for `id`, defaults `images` and `toolCalls` to empty arrays, and sets `timestamp` to 0 (unknown). Same pattern as the `Model` metadata gap — the adapter constructs full `Message` atoms from incomplete backend data.

**Intentionally excluded endpoints** (not needed by the React frontend in current scope):
- `POST /api/agent/<name>/call` and `GET /api/agents` — agent proxy, internal orchestration only
- `POST /api/chat` (non-streaming) — superseded by streaming endpoint for the UI
- `GET /static/images/<filename>` — not an adapter; images are served directly by Flask and referenced by URL in `ImageAttachment.src`

When the Flask backend is eventually refactored with proper response schemas, only these adapter files change.

---

## 9. Routing

```typescript
<BrowserRouter>
  <Routes>
    <Route path="/" element={<ChatPage />} />
    {/* Future routes */}
    <Route path="/models/:name" element={<ModelPage />} />
  </Routes>
</BrowserRouter>
```

Flask catch-all serves `index.html` for all non-`/api/` paths, enabling client-side routing with browser refresh support.

---

## 10. What Gets Deleted

After the React frontend is complete and verified:

- `INDEX_HTML` variable in `main.py` (~580 lines of HTML/JS/CSS)
- `GET /` route (template render)
- `GET /main.css` route
- `main.css` file (906 lines — ported to Tailwind + theme variables)
- All inline JavaScript (ported to React components + hooks)

**What stays untouched in main.py:**
- All `/api/*` routes
- WebSocket handler
- ToolCallFixerMiddleware
- LangGraph checkpointer
- ChromaDB RAG
- Authentication middleware
- CLI interface
- Agent proxy endpoints

---

## 11. Future Considerations (Out of Scope)

These are not part of this refactor but influenced design decisions:

- **PostgreSQL model registry** — `Model` atom is designed as a future DB entity with fields for usage tracking, maker info, licensing
- **User auth** — context providers are structured to accept a future `AuthProvider` at the top of the hierarchy
- **Ad integration** — React Router enables per-route ad placements; atomic component structure provides clean insertion points
- **Model query page** — `Model` atom + `/models/:name` route stub ready for a search/browse interface
- **Multi-user analytics** — `Model` atom includes fields for tracking (usage counts, per-user preferences) when Postgres arrives
- **Backend refactor** — adapter pattern isolates the frontend from backend response shape changes
