# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- **Dev server:** `npm run dev` (Vite on port 5173, proxies `/api` and `/static` to Flask backend on port 5000)
- **Build:** `npm run build` (runs `tsc -b && vite build`, outputs to `dist/`)
- **Lint:** `npm run lint` (ESLint with TypeScript + React hooks/refresh plugins)
- **Test all:** `npx vitest run`
- **Test single file:** `npx vitest run src/path/to/file.test.ts`
- **Test watch:** `npx vitest`

Tests use Vitest with jsdom environment, globals enabled, and `@testing-library/react` + `@testing-library/jest-dom`.

## Architecture

React 18 + TypeScript frontend for Atomic Chat, backed by a Flask/LangChain/Ollama Python backend.

### Provider hierarchy (App.tsx)

```
BrowserRouter > AuthProvider > ThemeProvider > AuthGate
  └─ PreferencesProvider > ModelProvider > ToolProvider > ChatProvider > WebSocketProvider > Routes
```

Authentication gates all inner providers — unauthenticated users see `LoginPage`.

### Key layers

- **`src/atoms/`** — Pure data types and factory functions (no React). `Message`, `StreamEvent`, `Model`, `Tool`, `Agent`, `User`. These are the shared type definitions, not Jotai atoms.
- **`src/api/`** — Fetch wrappers for backend endpoints (`/api/chat/stream`, `/api/models`, `/api/tools`, `/api/auth/*`, `/api/conversations`, `/api/preferences`). All use `credentials: 'include'` for session auth.
- **`src/hooks/`** — React hooks that compose atoms + API calls (`useChat`, `useStream`, `useModels`, `useTools`, `useTheme`, `useAuth`, `useWebSocket`).
- **`src/providers/`** — Context providers that wrap hooks into React context (`ChatProvider`, `AuthProvider`, `ModelProvider`, `ToolProvider`, `ThemeProvider`, `PreferencesProvider`, `WebSocketProvider`).
- **`src/components/`** — Atomic design: `atoms/` (Button, Input, Select, Badge, Icon, Modal), `molecules/` (MessageBubble, ModelSelect, ChatInput, ToolChip, ConversationItem), `organisms/` (Sidebar, InputBar, TopBar, MessageList, ConversationList, Lightbox, DashboardNav, ProfilePanel, ApiKeyPanel, ConnectionsPanel).
- **`src/pages/`** — Route-level components: `ChatPage`, `LoginPage`, `DashboardPage`.

### Streaming chat

Chat uses NDJSON streaming over `POST /api/chat/stream`. The `useStream` hook reads from a `ReadableStream`, parses NDJSON lines via `parseStreamLine` (in `atoms/stream.ts`), and dispatches `StreamEvent`s (`token`, `tool_call`, `tool_result`, `image`, `error`, `meta`). `ChatProvider` manages message state and conversation tracking.

### Styling

Tailwind CSS v4 via `@tailwindcss/vite` plugin. Uses CSS custom properties for theming (e.g., `var(--bg-base)`, `var(--text-muted)`).
