# User Dashboard Design

**Date:** 2026-03-17
**Status:** Approved
**Scope:** User dashboard with conversation history, profile, API key management, connections stub, and user preferences

---

## 1. Overview

Add a user dashboard at `/dashboard` with a left navigation and swappable content panels. The dashboard provides conversation history (with search and folders), profile management, API key CRUD, and a stub for managing external AI connections. User preferences (theme, save mode, selected tools) are persisted server-side.

---

## 2. Database Changes

### New tables

**conversations**

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| user_id | UUID | FK → users |
| title | VARCHAR(255) | Auto-generated from first message or user-set |
| folder | VARCHAR(128) | Nullable, for grouping |
| model | VARCHAR(128) | LLM model used, for restoring on resume |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | Updated on new message |

**conversation_messages**

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| conversation_id | UUID | FK → conversations, cascade delete |
| role | VARCHAR(16) | user/assistant/error |
| content | TEXT | Message body |
| images | JSONB | Array of image attachments |
| tool_calls | JSONB | Array of tool call info |
| created_at | TIMESTAMP | |

### Modified tables

**users** — add column:

| Column | Type | Notes |
|--------|------|-------|
| preferences | JSONB | Default `{}`, PostgreSQL JSONB for indexing support |

### Preferences schema

```json
{
  "save_mode": "auto" | "prompt" | "never",
  "theme": "<theme-id>",
  "selected_tools": ["read", "write", "ls", ...]
}
```

Defaults for new users:
- `save_mode`: `"auto"`
- `theme`: system default
- `selected_tools`: filesystem tools only (`read`, `info`, `ls`, `tree`, `write`, `append`, `replace`, `insert`, `delete`, `copy`, `move`, `mkdir`, `grep`, `find`, `definition`)

---

## 3. Routing & Navigation

### Routes

| Path | Component | Notes |
|------|-----------|-------|
| `/` | ChatPage | Existing chat interface |
| `/dashboard` | DashboardPage | New dashboard |
| `/login` | LoginPage | Existing, via AuthGate |

### Top bar changes

- Replace username + logout text with user avatar/icon (right-aligned)
- Avatar uses `avatar_url` from OAuth, falls back to generic user icon
- Click opens dropdown menu: "Dashboard", "Logout"
- Menu expandable for future items

### Dashboard ↔ Chat navigation

- Chat → Dashboard: avatar dropdown → "Dashboard"
- Dashboard → Chat: "Back to Chat" link in dashboard left nav

---

## 4. Dashboard Layout

Single page component (`DashboardPage`) with:
- Left nav sidebar with section links
- Main content area that swaps based on selected section (client-side state, no nested routes)

### Left nav sections

1. **Conversations** (default)
2. **Profile**
3. **API Keys**
4. **Manage Connections**

---

## 5. Conversation Lifecycle

### Save modes

| Mode | Behavior |
|------|----------|
| **auto** (default) | Conversation created in DB on first message sent. All messages persist in real-time. "New Conversation" starts fresh — no modal. |
| **prompt** | Nothing persists until user clicks "New Conversation". Modal appears with save/discard option. |
| **never** | Conversations are always ephemeral. "New Conversation" clears chat immediately, no modal, no persistence. |

### "New Conversation" button

- Appears at top of chat area, only after the first message is sent
- Behavior adapts based on save mode (see above)

### Save/discard modal (prompt mode only)

- Centered modal overlay
- Shows auto-generated title (first ~50 chars of first user message)
- Editable text input for title
- Optional folder dropdown (existing folders + "New folder")
- Two buttons: "Save" and "Discard"
- Save → persists conversation + messages, clears chat
- Discard → clears chat, nothing saved

### Auto-save flow (auto mode)

1. User sends first message
2. Backend creates conversation record, returns `conversation_id`
3. All subsequent messages are saved with that `conversation_id`
4. "New Conversation" button clears chat, next message creates a new conversation

### Conversation title

- Auto-generated: first ~50 characters of first user message
- Displayed above the date separator in chat area
- Pencil icon next to title for renaming (only when conversation is saved)
- Rename sends PATCH to backend

### Resuming a conversation

- From dashboard Conversations list, click a conversation
- Navigates to `/` with that conversation loaded
- Messages fetched from backend, rendered in chat area

---

## 6. Dashboard Panels

### Conversations

- **Search bar** at top — searches titles and message content (`ILIKE` queries)
- **Folder filter** — collapsible folder list in sidebar/filter area
- **Conversation list** — each item shows: title, date, preview snippet, folder tag
- **Click** → navigates to chat with that conversation loaded
- **Action menu** (right-click or icon): rename, move to folder, delete

### Profile (stub)

- Displays: username, email, avatar, auth method, role
- Editable fields: username, email
- Password change section (local auth users only)
- Placeholder text for future expansion

### API Keys

- **Table**: key prefix, label, created date, last used date
- **"Create Key" button** → modal with label input → displays raw key once with copy button and warning
- **Revoke button** per key with confirmation dialog

### Manage Connections (stub)

- "Add Connection" placeholder button (disabled)
- Text: "Anthropic, Cohere, Mistral, and more — coming soon"

---

## 7. Backend API Endpoints

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/conversations` | Create conversation (title, folder) |
| GET | `/api/conversations` | List user's conversations (supports `?q=` search, `?folder=` filter) |
| GET | `/api/conversations/<id>` | Get conversation with messages |
| PATCH | `/api/conversations/<id>` | Update title, folder |
| DELETE | `/api/conversations/<id>` | Delete conversation + messages |
| POST | `/api/conversations/<id>/messages` | Append message to conversation |

Pagination: `GET /api/conversations` supports `?page=1&limit=20` (default 20). `GET /api/conversations/<id>` supports `?page=1&limit=20` for messages (default 20, newest first). Frontend loads more on scroll.

### User preferences

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/auth/preferences` | Get current user's preferences |
| PATCH | `/api/auth/preferences` | Merge-update preferences |

### Profile

| Method | Path | Description |
|--------|------|-------------|
| PATCH | `/api/auth/profile` | Update username (3-64 chars, unique), email (unique). Returns 409 on conflict. |
| POST | `/api/auth/password` | Change password. Body: `{current_password, new_password}`. Requires min 8 chars. Returns 400 if current password wrong. OAuth-only users get 403. |

### Existing endpoints (no changes)

- `GET/POST/DELETE /api/auth/keys` — API key management
- `GET /api/auth/me` — current user (will include preferences in response)

---

## 8. Frontend Components

### New pages

- `DashboardPage` — layout with left nav + content area

### New organisms

- `DashboardNav` — left navigation sidebar
- `ConversationList` — search, folder filter, conversation items
- `ProfilePanel` — user profile display/edit
- `ApiKeyPanel` — key table + create/revoke
- `ConnectionsPanel` — stub placeholder

### New molecules

- `UserMenu` — avatar + dropdown (Dashboard, Logout)
- `SaveConversationModal` — centered modal for prompt save mode
- `ConversationItem` — single row in conversation list
- `ApiKeyRow` — single row in key table
- `CreateKeyModal` — modal for key creation + reveal
- `ConversationTitle` — title display + pencil rename icon (above date separator in chat)
- `NewConversationButton` — appears after first message sent

### New atoms

- `Avatar` — renders user avatar or fallback icon
- `Modal` — reusable centered modal overlay (extracted from Lightbox pattern)
- `DropdownMenu` — reusable positioned dropdown

### New API adapters

- `api/conversations.ts` — CRUD for conversations
- `api/preferences.ts` — get/update preferences

### New/modified providers

- `PreferencesProvider` — loads preferences on auth, provides to app
- Modify `ChatProvider` — integrate conversation persistence based on save mode
- Modify `ToolProvider` — initialize selected tools from preferences
- Modify `ThemeProvider` — initialize theme from preferences

---

## 9. Chat Integration Changes

### ChatProvider modifications

- Track `currentConversationId` state
- On `sendMessage`:
  - If auto mode and no current conversation: POST `/api/conversations`, set ID
  - POST message to `/api/conversations/<id>/messages`
- On "New Conversation": reset `currentConversationId`, clear messages
- On resume from dashboard: set `currentConversationId`, fetch messages

### Streaming persistence (backend-driven)

The `conversation_id` is passed as part of the `/api/chat/stream` request body. The backend handles all persistence:

1. Frontend sends `{ message, conversation_id }` to `/api/chat/stream`
2. Backend persists the user message to `conversation_messages`
3. Backend streams the LLM response as before
4. On stream completion, backend persists the assistant message (with tool calls, images)
5. Frontend does NOT call `POST /api/conversations/<id>/messages` separately during chat — that endpoint is for bulk import or manual additions only

This avoids race conditions between frontend and backend persistence paths.

### Per-user tool state

The current global `_state["selected_tools"]` is replaced with per-user tool selection:

- `/api/tools/select` and `/api/tools/deselect` read/write from the authenticated user's `preferences.selected_tools`
- The `/api/chat/stream` endpoint reads selected tools from the current user's preferences
- Unauthenticated requests (API key users) fall back to the global default (filesystem tools)
- The `ToolProvider` initializes from the user's preferences on login

### Deprecation of `_state["history"]`

The global in-memory `_state["history"]` and `/api/history` endpoints are deprecated:

- **Auto/prompt modes**: conversation_messages table is the source of truth. The backend still maintains `_state["history"]` as a per-request LLM context window (loaded from the conversation's messages), but it is not the persistence layer.
- **Never mode**: `_state["history"]` remains as the ephemeral LLM context, cleared on "New Conversation".
- `GET /api/history` and `DELETE /api/history` remain functional but read/write the in-memory context only. Frontend stops calling these directly — ChatProvider manages history through the conversations API instead.

---

## 10. Preferences Loading Flow

1. User authenticates (login, OAuth, or session restore)
2. `GET /api/auth/me` returns user data including preferences (add `preferences` to `_user_json` response)
3. `PreferencesProvider` stores preferences in context
4. `ThemeProvider` reads initial theme from preferences
5. `ToolProvider` reads initial selected tools from preferences
6. `ChatProvider` reads save mode from preferences
7. Any preference change → `PATCH /api/auth/preferences` → update context

### Theme precedence

On auth completion: server-side `preferences.theme` wins. If not set (new user), fall back to localStorage cache (`agentic-theme`), then system default. On theme change, write to both server preferences and localStorage (localStorage acts as fast cache for next page load before auth completes).

### Frontend type updates

Add `preferences?: Preferences` to the `User` interface in `atoms/user.ts`. Define `Preferences` type:

```typescript
interface Preferences {
  save_mode?: 'auto' | 'prompt' | 'never';
  theme?: string;
  selected_tools?: string[];
}
```
