# Task-Aware Tool Curation Design

**Date:** 2026-03-23
**Goal:** Replace the single-model prepass with a two-agent pipeline of lightweight 1.7B workers — a Task Extractor that maintains a per-conversation task list, and a Tool Curator that recommends workflow groups when the active tools don't cover the tasks. Users approve or dismiss recommendations via a chip in the input bar.

---

## 1. Problem

The current prepass (`prepass.py`) is a single 1.7B model that sees only the raw user message and guesses which tools the agent needs. It has no conversation context, so follow-ups like "try again" produce wrong or empty tool sets. It cannot be fixed by feeding it more context — the job is too complex for one small model with one prompt.

---

## 2. Architecture

Two sequential 1.7B workers with a shared `conversation_tasks` table between them:

```
User sends message
        │
        ▼
┌─────────────────┐
│  Task Extractor  │  Reads: user message + recent conversation history
│     (1.7B #1)    │  Writes: new tasks to conversation_tasks (or "no new tasks")
│                  │  Output: { new_tasks: bool, task_list: [...] }
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Tool Curator    │  Reads: task_list + user's active tools + workflow registry
│     (1.7B #2)    │  Output: pass-through OR { recommend: ["Web Tools"], tooltip: "..." }
└────────┬────────┘
         │
    ┌────┴─────┐
    │          │
 pass-through  recommend
    │          │
    │          ▼
    │     Frontend shows chip
    │     User accepts/dismisses
    │          │
    ├──────────┘
    ▼
  Agent gets message + final tool set
```

### Short-circuit rule

If the Task Extractor reports `new_tasks: false`, the Tool Curator skips inference entirely and passes through the same tools as the previous turn. This eliminates latency on follow-ups.

---

## 3. Conversation Tasks

### Schema

```sql
CREATE TABLE conversation_tasks (
    id          VARCHAR(36) PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id  VARCHAR(36) REFERENCES conversation_messages(id) ON DELETE SET NULL,
    title       TEXT NOT NULL,
    status      VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX ix_conversation_tasks_conversation ON conversation_tasks(conversation_id);
```

### Status values

- `pending` — extracted, not yet acted on
- `active` — agent is working on it (set by main agent via tool result signals)
- `done` — completed

### SQLAlchemy model

```python
class ConversationTask(Base):
    __tablename__ = "conversation_tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(String(36), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True)
    title = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), default=_now)

    conversation = relationship("Conversation")
```

### PM-forward compatibility

When the project management workflow lands, it will introduce:

- `projects` table
- `project_tasks` table with: `project_id`, `parent_task_id`, `assignee_id`, `priority`, `due_date`
- `project_tasks.promoted_from` FK → `conversation_tasks.id` for lineage

Nothing in `conversation_tasks` needs to change. Promotion is a one-way copy operation.

---

## 4. Workflow Group Registry

Static Python dict mapping group names to tool names and a short tooltip. This is the unit of recommendation — the Tool Curator recommends groups, not individual tools.

```python
WORKFLOW_GROUPS: dict[str, WorkflowGroup] = {
    "Filesystem": WorkflowGroup(
        tools=["read", "info", "ls", "tree", "write", "append",
               "replace", "insert", "delete", "copy", "move", "mkdir"],
        tooltip="File reading, writing, and directory operations",
    ),
    "Code Search": WorkflowGroup(
        tools=["grep", "find", "definition"],
        tooltip="Search code by pattern, filename, or symbol definition",
    ),
    "Web Tools": WorkflowGroup(
        tools=["web_search", "fetch_url", "webscrape", "find_all",
               "find_download_link"],
        tooltip="Web scraping, search, and navigation",
    ),
    "Ecommerce": WorkflowGroup(
        tools=["ebay_search", "ebay_sold_search", "ebay_deep_scan",
               "amazon_search", "craigslist_search", "craigslist_multi_search",
               "cross_platform_search", "deal_finder", "enrichment_pipeline"],
        tooltip="Product search across eBay, Amazon, and Craigslist",
    ),
    "Accounting": WorkflowGroup(
        tools=[...],  # all 21 accounting tool names
        tooltip="Double-entry bookkeeping, journal entries, and financial reports",
    ),
    # Future: "ERP/Inventory", "ERP/Invoicing", "CRM", etc.
}
```

### Data class

```python
@dataclass(frozen=True)
class WorkflowGroup:
    tools: list[str]
    tooltip: str
```

### API endpoint

```
GET /api/workflows → { groups: [{ name, tooltip, tool_count, tools: [name, ...] }] }
```

Consumed by the frontend sidebar tool browser and the recommendation chip.

---

## 5. Task Extractor (1.7B #1)

### Input

- The user's current message
- Last 5 conversation messages (for context on follow-ups)
- Current task list for this conversation

### Prompt

```
You are a task extraction agent. Read the user's message and conversation
context, then decide if there are new tasks.

Current tasks:
{task_list_or_"(none)"}

Recent conversation:
{last_5_messages}

User message: "{user_message}"

Rules:
- A "task" is a concrete action the user wants the agent to perform.
- Follow-ups like "try again", "format that differently", "now do X with that"
  are NOT new tasks — they modify existing tasks.
- If the message contains new tasks, return a JSON array of task titles.
- If there are no new tasks, return an empty array.

Return ONLY a JSON array. Examples:
- New tasks: ["Scrape supplier pricing from URL", "Import prices into ledger"]
- No new tasks: []
```

### Output parsing

Same pattern as current prepass: strip `<think>` tags, extract JSON array, validate strings. If malformed, treat as no new tasks (safe default).

### Behavior

- Returns `[]` → no DB writes, signals `new_tasks: false` to Tool Curator
- Returns `["task A", "task B"]` → writes rows to `conversation_tasks`, signals `new_tasks: true`, passes full task list to Tool Curator

---

## 6. Tool Curator (1.7B #2)

### Short-circuit

If `new_tasks: false`, skip inference entirely. Return the same tool set as the previous turn (cached per conversation).

### Input (when new tasks exist)

- Full task list (pending + active)
- User's active tools (from preferences)
- Workflow group registry (name + tooltip only, not individual tools)

### Prompt

```
You are a tool curation agent. Given the user's tasks and their currently
active tools, decide if additional workflow groups are needed.

Tasks:
{task_list}

User's active tools: {user_tool_names}

Available workflow groups:
{group_name}: {tooltip}
...

Rules:
- Never remove tools the user has chosen.
- If the user's tools are sufficient for all tasks, return: {"action": "pass"}
- If additional groups would help, return:
  {"action": "recommend", "groups": ["Group Name"], "reason": "short tooltip reason"}
- Recommend the minimum set of groups needed.
- Keep the reason under 15 words.

Return ONLY JSON.
```

### Output parsing

Extract JSON object. Validate `action` field. If `action` is `"recommend"`, validate group names against the registry. Discard unknown group names. If no valid groups remain after filtering, treat as pass-through.

### Output

- `{"action": "pass"}` → proceed with user's active tools
- `{"action": "recommend", "groups": [...], "reason": "..."}` → send recommendation to frontend, wait for user response

---

## 7. Frontend Recommendation Chip

### NDJSON event

New stream event type emitted *before* the agent starts:

```json
{"recommendation": {"groups": ["Web Tools"], "reason": "Aids with web scraping tasks"}}
```

### UI

Rendered as a chip above the input bar (same area as the "tools still running" overlay):

```
┌──────────────────────────────────────────────────────┐
│  + Web Tools — Aids with web scraping tasks           │
│                                                      │
│   [Accept]        [Dismiss]                          │
└──────────────────────────────────────────────────────┘
```

- **Accept** → frontend sends confirmation back, agent starts with expanded tool set
- **Dismiss** → agent starts with user's original tools only
- No timeout — waits for user action. The message is paused.

### Interaction flow

1. User sends message
2. Backend runs Task Extractor → Tool Curator
3. If recommend: backend yields `{"recommendation": {...}}` and pauses the generator
4. Frontend shows chip, user clicks accept/dismiss
5. Frontend sends `POST /api/chat/recommend` with `{"conversation_id": "...", "accepted_groups": ["Web Tools"]}` (or empty array for dismiss)
6. Backend resumes the generator with the final tool set
7. Agent runs normally

### Stream atom update

```typescript
type StreamEvent =
  | { type: 'token'; token: string }
  | { type: 'tool_call'; tool: string; input: string }
  | { type: 'tool_result'; tool: string; output: string }
  | { type: 'image'; src: string; filename: string; sizeKb: number }
  | { type: 'error'; message: string }
  | { type: 'meta'; conversationId: string | null }
  | { type: 'recommendation'; groups: string[]; reason: string }  // NEW
```

---

## 8. Backend Flow (replacing current prepass)

### Current flow (delete)

```python
# main.py line 347-349
fallback_names = _get_user_selected_tools()
tool_names = select_tools(user_msg, fallback_names)
```

### New flow

```python
# 1. Run Task Extractor
new_tasks = extract_tasks(user_msg, conversation_id, db)

# 2. Run Tool Curator (short-circuits if no new tasks)
curation = curate_tools(conversation_id, user_tool_names, new_tasks)

if curation.action == "recommend":
    # Yield recommendation event, pause for user response
    yield json.dumps({"recommendation": {
        "groups": curation.groups,
        "reason": curation.reason,
    }}) + "\n"
    # Wait for accept/dismiss via separate endpoint
    # (see interaction flow above)

# 3. Resolve final tool names
final_tools = resolve_tools(user_tool_names, accepted_groups)
```

### Caching

Per-conversation cache: `conversation_id → last_tool_names`. Used by the Tool Curator to short-circuit when no new tasks exist. Stored in-memory (same as current `_llm_cache`).

---

## 9. Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `prepass.py` | Delete | Replaced by task_extractor.py + tool_curator.py |
| `task_extractor.py` | Create | 1.7B #1 — message → tasks |
| `tool_curator.py` | Create | 1.7B #2 — tasks → tool recommendations |
| `workflow_groups.py` | Create | Static registry of workflow groups |
| `auth/conversation_tasks.py` | Create | ConversationTask model |
| `alembic/versions/xxx_add_conversation_tasks.py` | Create | Migration |
| `main.py` | Modify | Replace prepass integration with new pipeline |
| `config.py` | Modify | Add TASK_EXTRACTOR_MODEL, TOOL_CURATOR_MODEL (both default qwen3:1.7b) |
| `frontend/src/atoms/stream.ts` | Modify | Add recommendation event type |
| `frontend/src/components/organisms/InputBar.tsx` | Modify | Add recommendation chip UI |
| `frontend/src/providers/ChatProvider.tsx` | Modify | Handle recommendation event + accept/dismiss flow |
| `frontend/src/api/chat.ts` | Modify | Add recommendation response endpoint call |

---

## 10. What This Does NOT Include

- Project tasks / PM workflow (future)
- Workflow groups in the sidebar UI (covered by tool explorer spec)
- Interactive tool parameter forms (covered by tool explorer spec)
- Task list UI in the sidebar (future — surface conversation_tasks to user)
- Auto-promotion of conversation tasks to project tasks (future)
