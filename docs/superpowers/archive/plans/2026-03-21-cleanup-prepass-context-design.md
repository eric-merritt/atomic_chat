# Cleanup, Tool Pre-Pass, and Context Pipeline Design

**Date:** 2026-03-21
**Goal:** Maximize useful context for the agent by removing dead code, dynamically selecting tools, and wiring conversation history into the chat pipeline.

---

## 1. Cleanup

### Files to Delete

| File | Reason |
|------|--------|
| `index.py` | Broken RAG indexer, references missing config constants |
| `index_repo.py` | Same — orphaned RAG experiment |
| `inspect_db.py` | Chroma DB inspector for a DB that doesn't exist |
| `run_agents.py` | Launches subagent MCP servers that nothing calls |
| `tools.py` (root) | Shadowed by `tools/` package — Python resolves `from tools import` to `tools/__init__.py`, making this file dead code |
| `agents/base.py` | Only referenced by other agent files |
| `agents/codesearch.py` | Only referenced by `run_agents.py` |
| `agents/dispatcher.py` | Only referenced by `run_agents.py` |
| `agents/ecommerce.py` | Only referenced by `run_agents.py` |
| `agents/filesystem.py` | Only referenced by `run_agents.py` |
| `agents/web.py` | Only referenced by `run_agents.py` |
| `agents/__init__.py` | Empty package init |
| `agents/continue.md` | Notes file in agents dir |

### Files to Clean Up

| File | Change |
|------|--------|
| `main.py` | Remove dead import: `from config import AGENT_PORTS, agent_url` |
| `config.py` | Remove `AGENT_PORTS`, `AGENT_MODELS`, `agent_url()`. Keep `RATE_LIMITS` and `MAX_RETRIES` |
| `tests/test_config.py` | Remove tests for `AGENT_PORTS` and `agent_url` (deleted from config.py) |

### Files to Keep (standalone utilities, not part of main flow)

| File | Reason |
|------|--------|
| `client_agent.py` | WebSocket client, independent utility |
| `credentials.py` | Encrypted credential CLI, independent utility |

---

## 2. Tool Pre-Pass

### Problem

All tool schemas are bound to the agent at build time. With 64 tools, the model has to reason about which tool to use from a large set. Smaller tool sets produce more deterministic tool selection, especially with Qwen models.

### Solution

A lightweight LLM pre-pass selects relevant tools before building the agent.

### Configuration

- **Pre-pass model:** `qwen3:1.7b` (must be pulled locally via `ollama pull qwen3:1.7b`)
- **Config location:** New constant in `config.py`: `PREPASS_MODEL = os.environ.get("PREPASS_MODEL", "qwen3:1.7b")`
- **Fallback if model unavailable:** Skip pre-pass, fall back to user's `selected_tools` preference (or `DEFAULT_TOOL_NAMES` if no preference set)

### Flow

```
User message arrives at /api/chat/stream
  │
  ▼
Pre-pass model (PREPASS_MODEL)
  receives: user message + compact tool index (names + one-line descriptions)
  returns: JSON array of tool names needed for this task
  │
  ▼
Fetch full schemas for selected tools from https://tools.eric-merritt.com/<name>
  │
  ▼
Build agent with only selected tools bound
  │
  ▼
Run conversation turn
```

### Pre-Pass Prompt

```
Given the user's request, select which tools are needed.
Return ONLY a JSON array of tool names. Select the minimum set needed.

Available tools:
- read: Read a file and return its contents with line numbers
- web_search: Search the web using DuckDuckGo
- ebay_search: Search eBay Buy It Now listings
- craigslist_search: Search Craigslist in a specific city
- fetch_url: Fetch a URL and return its text content
...

User request: "find inexpensive listings for 'x' product"

Response: ["ebay_search", "craigslist_multi_search", "deal_finder"]
```

### Compact Tool Index

The `GET /` endpoint on `tools.eric-merritt.com` currently returns full schemas (name, description, params). The pre-pass only needs names + first-line descriptions to keep tokens low.

**Approach:** The main server fetches the full tool list from `tools.eric-merritt.com/` at startup, strips it down to `{name: first_line_of_description}` pairs, and caches that as the compact index. No changes needed to the tool server.

### Failure Handling

| Failure | Behavior |
|---------|----------|
| Pre-pass model not available | Log warning, fall back to user's `selected_tools` or `DEFAULT_TOOL_NAMES` |
| Pre-pass returns malformed JSON | Fall back to user's `selected_tools` or `DEFAULT_TOOL_NAMES` |
| Pre-pass returns empty array | Fall back to user's `selected_tools` or `DEFAULT_TOOL_NAMES` |
| Pre-pass returns unknown tool names | Filter out unknown names, use remaining valid ones. If none valid, fall back |
| Tool server unreachable | Use locally imported `ALL_TOOLS` as fallback (current behavior) |

### Caching

- **Scope:** Per-conversation. Each conversation caches its most recent tool selection.
- Pre-pass runs every turn
- If the pre-pass returns the same tools as the previous turn in this conversation, skip rebuilding the agent
- If tools change, rebuild with the new set

---

## 3. Context Pipeline

### Problem

The `/api/chat/stream` endpoint currently sends system prompt + a single user message every request. No conversation history. The `ConversationMessage` table exists in Postgres with full CRUD routes, but the chat endpoint doesn't read from or write to it.

### Solution

Wire conversation history into the chat pipeline. Scope is current conversation only — prior conversations are not loaded into context.

### Conversation ID Flow

The frontend already manages conversations via the CRUD routes at `/api/conversations`. The chat endpoint needs to accept a `conversation_id`:

- **Request body:** `{"message": "...", "conversation_id": "uuid-or-null"}`
- **If `conversation_id` is provided:** Load that conversation's messages as history
- **If `conversation_id` is null/omitted:** Auto-create a new `Conversation` row, return its `id` in the response so the frontend can track it going forward
- **First message of new conversation:** Title defaults to a truncated version of the first user message (first 60 chars)

### Message Assembly

```
System prompt
  │
  ▼
Current conversation messages (from DB, ordered by created_at)
  │
  ▼
Current user message
```

### Message Storage Format

Messages are stored in the `ConversationMessage` table using the existing schema:

| Role | `role` column | `content` column | `tool_calls` column |
|------|---------------|-------------------|---------------------|
| User message | `"user"` | The user's text | `[]` |
| Assistant text response | `"assistant"` | The response text | `[]` |
| Assistant tool call | `"assistant"` | `""` | `[{"name": "...", "args": {...}}]` |
| Tool result | `"tool"` | The tool's output (truncated to 4000 chars) | `[{"name": "tool_name"}]` |

When replaying history into the LangChain message list:
- `role="user"` → `HumanMessage(content=...)`
- `role="assistant"` with empty `tool_calls` → `AIMessage(content=...)`
- `role="assistant"` with `tool_calls` → `AIMessage(content="", tool_calls=[ToolCall(...)])`
- `role="tool"` → `ToolMessage(content=..., name=...)`

### History Rules

- **Current conversation only** — no prior conversations loaded into context
- **Full message content** for human and assistant messages
- **Tool results truncated** — cap individual tool result messages at 4000 chars when replaying as history
- **Save both sides** — after each agent turn, persist the user message and agent response to the DB
- **Tool call sequences** — when the agent calls a tool, save the tool call as an assistant message, then save the tool result as a tool message. This preserves the correct LangChain message ordering for replay.

### Prior Conversation Access (Future)

A `search_conversations` tool gated behind a user setting. When enabled, the agent can search the `ConversationMessage` table across prior conversations using text search and retrieve relevant snippets. This is a separate piece of work — not in scope for this spec.

### Model Context

- Target model: `qwen2.5-coder-abliterate:14b` with 128k token context window
- With 128k tokens, most single-conversation histories fit comfortably
- The 4000-char cap on tool results in history handles edge cases (repeated large search results)

---

## Architecture After Changes

```
User message + conversation_id
  │
  ▼
Pre-pass model ──► tools.eric-merritt.com/ (compact tool index, cached at startup)
  │                        │
  │                        ▼
  │               tools.eric-merritt.com/<name> (full schemas for selected tools)
  │
  ▼
Build agent (selected tools only, skip if same as last turn)
  │
  ▼
Load conversation history (current conversation_id, from ConversationMessage table)
  │
  ▼
Assemble messages: system prompt + history + user message
  │
  ▼
Agent executes (calls tools via bound LangChain tools)
  │
  ▼
Save user message + agent response + tool calls/results to DB
  │
  ▼
Stream response to frontend (include conversation_id in response)
```

---

## What This Does NOT Cover

- **Ecommerce tool consolidation** — collapsing platform-specific tools into generic `search_listings` + site reconnaissance system. Separate spec, lower priority.
- **Prior conversation search tool** — `search_conversations` for cross-conversation context. Future work.
- **RAG / vector embeddings** — removed in cleanup. If needed later, will be a fresh design.
