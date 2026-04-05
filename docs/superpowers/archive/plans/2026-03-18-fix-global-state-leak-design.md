# Fix Global State Leak Between Users

**Date:** 2026-03-18
**Status:** Approved

## Problem

The app uses a module-level `_state` dictionary in `main.py` (line 206) that is shared across all users and requests. When User A sends a message, it appends to `_state["history"]`. When User B sends a message, the LLM receives User A's history as context. This caused a real incident: one user's filesystem tool error was surfaced to a different user on a different computer.

The global `_state` holds three things that should not be global:
- `history` — conversation messages shared across all users
- `model` — one user changing the model affects everyone
- `system_prompt` — mutable by any user, affects all subsequent conversations

## Solution

Replace all global state with per-user, per-conversation state backed by the existing database layer (`Conversation`, `ConversationMessage` models). Add a `/conversations` slash command for in-chat conversation switching.

## Changes

### 1. Remove `_state["history"]` — DB-backed conversation history

- Delete the `_state` dictionary from `main.py`. This also removes the `selected_tools` key, which is already handled by per-user preferences via `_get_user_selected_tools()`.
- Replace `_history_to_messages()` with a new function `_load_conversation_messages(conversation_id, user_id)` that queries `ConversationMessage` rows for the given conversation, filtered by `user_id` ownership, and converts them to LangChain `HumanMessage`/`AIMessage` objects. Load the **last 50 messages** to stay within LLM context window limits.
- In `/api/chat/stream`, use this function instead of reading from `_state["history"]`. The `conversation_id` is already passed in the request body and auto-created when missing.
- Remove all `_state["history"].append(...)` calls. Message persistence already happens via `ConversationMessage` DB writes in `chat_stream()`.

### 2. Remove `_state["model"]` — per-conversation + user preference

- Model is already stored on `Conversation.model` (set at conversation creation time).
- `_build_agent()` gains a `conversation` parameter (the `Conversation` ORM object). It reads model from `conversation.model` first, then falls back to `current_user.preferences.get("model")`.
- `POST /api/models` writes directly to `User.preferences["model"]` instead of `_state["model"]`. Changing the model only affects future conversations — it does not clear or reset the current conversation.
- `GET /api/models` returns `current` from user preferences instead of `_state["model"]`.

### 3. Replace `_state["system_prompt"]` with a constant

Replace the mutable system prompt with a hardcoded constant focused on response discipline and anti-fabrication. No tool descriptions in the prompt (those belong in tool schemas). The new prompt covers:

- **No fabrication:** Must use tools for external data. Never guess file contents, search results, or current data. Report errors and empty results honestly.
- **Execute, don't instruct:** Never tell the user how to run a tool. Plan the steps, check available tools, execute anything possible. Only explain what cannot be done after exhausting all tools.
- **Tool vs. knowledge boundary:** Files/system state/search queries (products, prices, stock data, website links, news, weather, scores, jobs, real estate, reviews, documentation, anything expected to be current or real) require tools. General knowledge and reasoning are fine without tools.
- **Response format:** Present data as human-readable text. No JSON structure descriptions, no restating the question, no unsolicited context.

### 4. `/conversations` slash command

**Backend:** In `/api/chat/stream`, before invoking the agent, check if the trimmed message equals `/conversations`. If so:
- Query the DB for the current user's recent conversations (last 20, ordered by `updated_at` desc).
- Return a synthetic streaming response with `type: "conversations_list"` containing the conversation list.
- Do NOT persist the `/conversations` command or its response as `ConversationMessage` rows.
- Do NOT create a new conversation for this command.

**Response format:**
```json
{"type": "conversations_list", "conversations": [
  {"id": "abc-123", "title": "New Conversation", "updated_at": "2026-03-17T..."},
  ...
]}
{"done": true}
```

**Frontend:** In `MessageBubble.tsx`, detect messages that contain conversation list data. Render each conversation as a clickable row showing title and relative timestamp. Clicking a row calls `loadConversation(id)` from `ChatProvider`, which already handles fetching messages from the DB and setting the active `conversationId` + URL param.

**Stream parser:** The current `parseStreamLine` in `stream.ts` uses property-name detection (`'chunk' in raw`, `'tool_call' in raw`). The `conversations_list` event uses a `type` field (like the existing `meta` event). Add a new branch: `if (raw.type === 'conversations_list')` to parse this event and surface the conversations array to `ChatProvider`.

### 5. Remove dead endpoints

| Endpoint | Action |
|---|---|
| `POST /api/chat` | Remove entirely (frontend uses `/api/chat/stream` only) |
| `GET /api/history` | Remove (replaced by `GET /api/conversations/<id>`) |
| `DELETE /api/history` | Remove (replaced by `DELETE /api/conversations/<id>`) |
| `POST /api/system` | Remove (prompt is now a constant) |
| `GET /api/system` | Remove (prompt is a constant, no need to serve it) |

### 6. Add `@login_required` to unprotected endpoints

| Endpoint | Current auth | Change |
|---|---|---|
| `GET /api/models` | None (only `auth_guard` middleware) | Add `@login_required` |
| `POST /api/models` | None | Add `@login_required` |
| `GET /api/tools/<int:index>` | None | Add `@login_required` |

### 7. CLI mode

Left as-is. CLI mode is single-user by nature and will continue using its own local state within the interactive functions. No changes to `cli_chat()`, `cli_model_picker()`, or `cli_tool_browser()`.

## Files modified

| File | Changes |
|---|---|
| `main.py` | Remove `_state`, remove dead endpoints, add auth decorators, rewrite `chat_stream()` to use DB history, add `/conversations` intercept, new constant system prompt |
| `frontend/src/components/molecules/MessageBubble.tsx` | Render conversation list items as clickable links |
| `frontend/src/providers/ChatProvider.tsx` | Handle `conversations_list` stream event type |
| `frontend/src/atoms/stream.ts` | Add `conversations_list` to `StreamEvent` type |

## Files removed

No files removed.

## Out of scope

- Markdown rendering in message bubbles
- Admin-only system prompt editing
- CLI mode refactoring
- Migration to per-user system prompts
