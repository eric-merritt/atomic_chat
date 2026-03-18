# Fix Global State Leak Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the global `_state` dictionary that leaks conversation history, model selection, and system prompt across all users, replacing it with per-user per-conversation DB-backed state.

**Architecture:** Remove `_state` from `main.py`. Chat history loads from `ConversationMessage` table per conversation. Model stored in user preferences. System prompt becomes a constant. Add `/conversations` slash command intercepted server-side. Remove dead endpoints and add auth decorators.

**Tech Stack:** Python/Flask, SQLAlchemy, LangChain, React/TypeScript, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-18-fix-global-state-leak-design.md`

---

## File Structure

| File | Action | Responsibility |
| --- | --- | --- |
| `main.py` | Modify | Remove `_state`, dead endpoints, rewrite `chat_stream()` and `_build_agent()`, add auth, new system prompt constant, `/conversations` intercept |
| `frontend/src/atoms/stream.ts` | Modify | Add `conversations_list` event type |
| `frontend/src/atoms/message.ts` | Modify | Add `conversationsList` field to `Message` |
| `frontend/src/providers/ChatProvider.tsx` | Modify | Handle `conversations_list` event, remove `clearHistory` dep on `/api/history` |
| `frontend/src/components/molecules/MessageBubble.tsx` | Modify | Render conversation list as clickable items |
| `frontend/src/api/history.ts` | Delete | Dead code — endpoints being removed |
| `frontend/src/api/system.ts` | Delete | Dead code — endpoints being removed |
| `frontend/src/api/__tests__/history.test.ts` | Delete | Tests for deleted module |
| `frontend/src/hooks/__tests__/useChat.test.tsx` | Modify | Remove `/api/history` reference from clearHistory test |

---

### Task 1: Rewrite all backend state management (atomic)

This task is atomic — all changes to `main.py` happen together to avoid a broken intermediate state where `_state` is removed but `_build_agent()` still references it.

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Replace `_state` with `SYSTEM_PROMPT` constant and `_cli_state`**

Find the `_state` dict (lines 206-264) and replace it with:

```python
# ── System prompt (constant) ────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a helpful assistant with access to tools. Use them.

## CRITICAL: No fabrication

You MUST use tools to answer questions that require external data. NEVER fabricate, guess,
or infer answers that should come from a tool call.

If a user asks you to read a file — call the read tool. Do not guess the contents.
If a user asks for search results — call the search tool. Do not make up listings.
If a tool returns an error — report the error honestly. Do not invent a plausible answer.
If a tool returns no results — say "no results found." Do not fill the gap with imagination.

When you have tool results, report ONLY what the tool returned. Nothing more.

## CRITICAL: Execute, don't instruct

You are NOT a tutorial. You are an executor. Your job is to DO things, not tell the user
how to do things.

NEVER respond with instructions for the user to follow. NEVER say "you can run...",
"try running...", "you could use...", "here's how to...", or "to do this, you would...".
The user asked YOU to do it. Not to be taught how.

When you receive a task:
1. Plan what steps are needed to accomplish it.
2. Review your available tools. Can any combination of them accomplish any of those steps?
3. If by ANY stretch of imagination a tool can execute the task or part of it — call the tool.
4. Only explain what you CANNOT do after you have exhausted every tool available to you.

If the user says "check what's in /tmp" — call ls or read. Do not say "you can run ls /tmp".
If the user says "find files matching *.log" — call find or grep. Do not say "try using find".
If the user says "search eBay for GPUs" — call ebay_search. Do not describe how eBay works.
If the user says "write a script to X" — call write to create the file. Do not paste code and
say "save this as...".

You have tools for a reason. Every time you tell the user to do something manually that you
could have done with a tool, you have failed at your job.

The ONLY acceptable time to give instructions is when you genuinely have no tool that can
perform the action. Even then, try harder — break the problem into smaller steps and check
again whether your tools can handle each step individually.

## When to use tools vs. your own knowledge

- Questions about files, directories, system state → ALWAYS use tools
- Search queries (products, prices, listings, stock data, website links, news articles,
  weather, sports scores, recipes, job postings, real estate, travel deals, local businesses,
  reviews, documentation, anything the user expects to be current or real) → ALWAYS use tools
- General knowledge, opinions, explanations, reasoning → your own knowledge is fine
- If unsure whether a tool is needed → use the tool

## Response format

- Present tool results as human-readable text. Extract the data, don't describe the structure.
- Do NOT say "The tool returned..." or describe JSON fields.
- Do NOT restate the user's question.
- Do NOT add unsolicited background context.
- If results are empty, say so. Do not stretch or fabricate.

Bad: "The tool returned a JSON object containing a list of items with fields such as title, price..."
Good: "1. EVGA RTX 3060 12GB - $189.00 (free shipping)"
"""

# ── CLI-only state (single-user, not used by web API) ───────────────────────
_cli_state = {
    "model": None,
    "system_prompt": SYSTEM_PROMPT,
    "history": [],
    "selected_tools": [],
}
```

- [ ] **Step 2: Remove dead endpoints**

Delete these functions entirely (locate by function name, not line number — lines will have shifted after Step 1):

- `get_system()` and `set_system()` — the `/api/system` GET and POST handlers
- `get_history()` and `clear_history()` — the `/api/history` GET and DELETE handlers
- `chat()` — the `/api/chat` POST handler (non-streaming)
- `_history_to_messages()` — helper only used by the deleted `chat()` endpoint

- [ ] **Step 3: Add `_load_conversation_messages()` helper**

Add above `_build_agent()`:

```python
def _load_conversation_messages(conversation_id: str, user_id: str) -> list:
    """Load the last 50 messages from a conversation as LangChain messages."""
    from auth.conversations import Conversation, ConversationMessage
    db = get_db()
    conv = db.query(Conversation).filter_by(id=conversation_id, user_id=user_id).first()
    if not conv:
        return []
    rows = (
        db.query(ConversationMessage)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(50)
        .all()
    )
    rows.reverse()  # chronological order
    msgs = []
    for r in rows:
        if r.role == "user":
            msgs.append(HumanMessage(content=r.content))
        elif r.role == "assistant":
            msgs.append(AIMessage(content=r.content))
    return msgs
```

- [ ] **Step 4: Rewrite `_build_agent()` for web API (conversation-aware)**

Replace the existing `_build_agent()` with a version that takes a `conversation` parameter and reads model from the conversation or user preferences — NOT from `_state`:

```python
def _build_agent(conversation=None):
    """Build a LangGraph agent for web API requests."""
    # Resolve model: conversation > user preference
    model_name = None
    if conversation and conversation.model:
        model_name = conversation.model
    if not model_name:
        prefs = current_user.preferences or {}
        model_name = prefs.get("model")
    if not model_name:
        raise ValueError("No model selected. Pick a model first.")

    llm = ToolCallFixerChatModel(
        model=model_name,
        temperature=0,
        base_url="http://localhost:11434",
    )

    selected_idx = set(_get_user_selected_tools())
    tools = [t for i, t in enumerate(ALL_TOOLS) if i in selected_idx] if selected_idx else []
    agent = create_agent(
        llm,
        tools,
        system_prompt=SYSTEM_PROMPT,
    )
    return agent
```

- [ ] **Step 5: Add `_build_cli_agent()` for CLI mode**

Add below `_build_agent()`:

```python
def _build_cli_agent():
    """Build a LangGraph agent for CLI mode (uses _cli_state)."""
    if not _cli_state["model"]:
        raise ValueError("No model selected. POST /api/models first.")

    llm = ToolCallFixerChatModel(
        model=_cli_state["model"],
        temperature=0,
        base_url="http://localhost:11434",
    )

    agent = create_agent(
        llm,
        list(ALL_TOOLS),
        system_prompt=_cli_state["system_prompt"],
    )
    return agent
```

- [ ] **Step 6: Rewrite model endpoints to use user preferences and add `@login_required`**

Replace `list_models()`:

```python
@app.route("/api/models", methods=["GET"])
@login_required
def list_models():
    """List locally available Ollama models."""
    try:
        models = ollama_client.list()
        names = [m.model for m in models.models]
        prefs = current_user.preferences or {}
        current = prefs.get("model")
        return jsonify({"models": names, "current": current})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

Replace `select_model()`:

```python
@app.route("/api/models", methods=["POST"])
@login_required
def select_model():
    """Select an Ollama model. Body: {"model": "name"}"""
    data = request.get_json(force=True)
    model = data.get("model")
    if not model:
        return jsonify({"error": "model required"}), 400
    db = get_db()
    prefs = dict(current_user.preferences or {})
    prefs["model"] = model
    current_user.preferences = prefs
    db.commit()
    return jsonify({"model": model})
```

Add `@login_required` to `tool_detail()`:

```python
@app.route("/api/tools/<int:index>", methods=["GET"])
@login_required
def tool_detail(index: int):
```

- [ ] **Step 7: Rewrite `chat_stream()` — DB history + `/conversations` intercept**

Replace the entire `chat_stream()` function:

```python
@app.route("/api/chat/stream", methods=["POST"])
@login_required
def chat_stream():
    """Streaming chat. Returns newline-delimited JSON."""
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "message required"}), 400

    # Slash command: /conversations
    if user_msg == "/conversations":
        from auth.conversations import Conversation
        db = get_db()
        convs = (
            db.query(Conversation)
            .filter_by(user_id=current_user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(20)
            .all()
        )
        conv_list = [
            {
                "id": c.id,
                "title": c.title,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in convs
        ]

        def gen_convs():
            yield json.dumps({
                "type": "conversations_list",
                "conversations": conv_list,
            }) + "\n"
            yield json.dumps({"done": True}) + "\n"

        return Response(
            stream_with_context(gen_convs()),
            mimetype="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    conversation_id = data.get("conversation_id")

    # Auto-create conversation if needed
    if not conversation_id:
        prefs = (current_user.preferences or {}) if hasattr(current_user, 'preferences') else {}
        save_mode = prefs.get("save_mode", "auto")
        if save_mode == "auto":
            from auth.conversations import Conversation
            db = get_db()
            user_model = (current_user.preferences or {}).get("model")
            conv = Conversation(
                user_id=current_user.id,
                title=user_msg[:50] if user_msg else "New Conversation",
                model=user_model,
            )
            db.add(conv)
            db.commit()
            conversation_id = conv.id

    # Persist user message
    conversation = None
    if conversation_id:
        from auth.conversations import Conversation, ConversationMessage
        db = get_db()
        conversation = db.query(Conversation).filter_by(
            id=conversation_id, user_id=current_user.id
        ).first()
        if conversation:
            db.add(ConversationMessage(
                conversation_id=conversation_id,
                role="user",
                content=user_msg,
            ))
            from datetime import datetime, timezone
            conversation.updated_at = datetime.now(timezone.utc)
            db.commit()

    try:
        agent = _build_agent(conversation)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Load history from DB (last 50 messages, includes the user msg we just saved)
    if conversation_id:
        messages = _load_conversation_messages(conversation_id, current_user.id)
    else:
        messages = [HumanMessage(content=user_msg)]

    def generate():
        from langchain_core.messages import ToolMessage
        yield json.dumps({"type": "meta", "conversation_id": conversation_id}) + "\n"

        full_response = ""
        tool_calls_collected = []
        try:
            for event in agent.stream({"messages": messages}, stream_mode="updates"):
                for node_name, node_output in event.items():
                    if "messages" not in node_output:
                        continue
                    for msg in node_output["messages"]:
                        tc = getattr(msg, "tool_calls", None)
                        if tc:
                            for call in tc:
                                tool_calls_collected.append({
                                    "tool": call.get("name", ""),
                                    "input": str(call.get("args", "")),
                                })
                                yield json.dumps({"tool_call": {
                                    "tool": call.get("name", ""),
                                    "input": str(call.get("args", "")),
                                }}) + "\n"
                        elif isinstance(msg, ToolMessage):
                            yield json.dumps({"tool_result": {
                                "tool": getattr(msg, "name", ""),
                                "output": str(msg.content)[:500],
                            }}) + "\n"
                        elif msg.content:
                            full_response = msg.content
                            yield json.dumps({"chunk": msg.content}) + "\n"
        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        # Persist assistant message
        if conversation_id:
            from auth.conversations import ConversationMessage
            db = get_db()
            db.add(ConversationMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                tool_calls=tool_calls_collected if tool_calls_collected else [],
            ))
            db.commit()

        yield json.dumps({"done": True, "full_response": full_response}) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 8: Update all CLI functions to use `_cli_state` and `_build_cli_agent()`**

In `cli_tool_browser()`, `cli_model_picker()`, `cli_chat()`, and the `main()` interactive menu, replace every `_state` reference with `_cli_state` and every `_build_agent()` call with `_build_cli_agent()`. Specific replacements:

- `cli_tool_browser()`: `_state["selected_tools"]` → `_cli_state["selected_tools"]`
- `cli_model_picker()`: `_state["model"]` → `_cli_state["model"]`
- `cli_chat()`: `_state["model"]` → `_cli_state["model"]`, `_state["history"]` → `_cli_state["history"]`, `_build_agent()` → `_build_cli_agent()`
- `main()` menu option 4: `_state["system_prompt"]` → `_cli_state["system_prompt"]`

Also update the `_history_to_messages` equivalent in `cli_chat()` — it builds messages inline from `_state["history"]`, change to `_cli_state["history"]`.

- [ ] **Step 9: Verify the server starts and removed endpoints are gone**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "
from main import app
c = app.test_client()
# Removed endpoints should 404 or 405
assert c.get('/api/system').status_code in (401, 404, 405), 'GET /api/system should be gone'
assert c.post('/api/system').status_code in (401, 404, 405), 'POST /api/system should be gone'
assert c.get('/api/history').status_code in (401, 404, 405), 'GET /api/history should be gone'
assert c.delete('/api/history').status_code in (401, 404, 405), 'DELETE /api/history should be gone'
print('OK — all removed endpoints confirmed gone')
"`

- [ ] **Step 10: Verify no `_state[` references remain in web API code**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && grep -n "_state\[" main.py`
Expected: Zero matches. All references should be `_cli_state[`.

- [ ] **Step 11: Commit**

```bash
git add main.py
git commit -m "fix: replace global _state with per-user DB-backed state

Remove _state dict that leaked history/model/prompt across users.
Chat history now loads from ConversationMessage table per conversation.
Model selection stored in user preferences.
System prompt is a constant focused on anti-fabrication.
Add /conversations slash command.
Remove dead endpoints: POST /api/chat, GET/DELETE /api/history, GET/POST /api/system.
Add @login_required to GET/POST /api/models, GET /api/tools/<index>.
CLI mode uses separate _cli_state and _build_cli_agent()."
```

---

### Task 2: Add `conversations_list` stream event and message type (frontend)

**Files:**
- Modify: `frontend/src/atoms/stream.ts`
- Modify: `frontend/src/atoms/message.ts`
- Modify: `frontend/src/providers/ChatProvider.tsx`

- [ ] **Step 1: Add `ConversationListItem` type and `conversations_list` event to `stream.ts`**

In `frontend/src/atoms/stream.ts`, add the type above the `StreamEvent` union and add the new variant:

```typescript
export type ConversationListItem = {
  id: string;
  title: string;
  updated_at: string | null;
};

export type StreamEvent =
  | { type: 'token'; token: string }
  | { type: 'tool_call'; tool: string; input: string }
  | { type: 'tool_result'; tool: string; output: string }
  | { type: 'image'; src: string; filename: string; sizeKb: number }
  | { type: 'error'; message: string }
  | { type: 'meta'; conversationId: string | null }
  | { type: 'conversations_list'; conversations: ConversationListItem[] };
```

In `parseStreamLine`, add a branch **after** the existing `meta` check (line 13):

```typescript
  if ('type' in raw && raw.type === 'conversations_list') {
    return { type: 'conversations_list', conversations: raw.conversations ?? [] };
  }
```

- [ ] **Step 2: Add `conversationsList` to `Message` type in `message.ts`**

In `frontend/src/atoms/message.ts`, add the import and optional field:

```typescript
import type { ConversationListItem } from './stream';
```

Add to the `Message` interface:

```typescript
export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  images: ImageAttachment[];
  toolCalls: ToolCallInfo[];
  timestamp: number;
  conversationsList?: ConversationListItem[];
}
```

- [ ] **Step 3: Handle `conversations_list` event in `ChatProvider.tsx`**

In `ChatProvider.tsx`, inside the `sendMessage` callback's `onEvent` switch statement (around line 79), add a case before the `default`/closing:

```typescript
          case 'conversations_list':
            setMessages((prev) => [
              ...prev,
              {
                ...createMessage('assistant', ''),
                conversationsList: ev.conversations,
              },
            ]);
            break;
```

- [ ] **Step 4: Run frontend lint**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama/frontend && npm run lint`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/atoms/stream.ts frontend/src/atoms/message.ts frontend/src/providers/ChatProvider.tsx
git commit -m "feat: add conversations_list stream event type and handler"
```

---

### Task 3: Render conversation list in MessageBubble

**Files:**
- Modify: `frontend/src/components/molecules/MessageBubble.tsx`

- [ ] **Step 1: Rewrite `MessageBubble` to handle conversation lists**

Replace the contents of `frontend/src/components/molecules/MessageBubble.tsx`:

```tsx
import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { Message } from '../../atoms/message';
import { useChat } from '../../hooks/useChat';

const roleClasses = {
  user: 'self-end bg-[var(--msg-user)]',
  assistant: 'self-start bg-[var(--msg-assistant)]',
  error: 'self-center bg-transparent text-[var(--danger)] text-center',
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function MessageBubble({ message }: { message: Message }) {
  const { loadConversation } = useChat();
  const [, setSearchParams] = useSearchParams();

  const handleConversationClick = useCallback((id: string) => {
    setSearchParams({ conversation: id });
    loadConversation(id);
  }, [loadConversation, setSearchParams]);

  // Render conversation list
  if (message.conversationsList && message.conversationsList.length > 0) {
    return (
      <div className="max-w-[75%] px-4 py-3 rounded-xl text-sm leading-relaxed animate-[msgIn_0.25s_ease-out] self-start bg-[var(--msg-assistant)]">
        <div className="text-[var(--text-muted)] mb-2 font-medium">Recent conversations:</div>
        <div className="flex flex-col gap-1">
          {message.conversationsList.map((conv) => (
            <button
              key={conv.id}
              onClick={() => handleConversationClick(conv.id)}
              className="text-left px-3 py-2 rounded-lg hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
            >
              <span className="text-[var(--accent)] font-mono">{conv.title}</span>
              <span className="text-[var(--text-muted)] text-xs ml-2">{timeAgo(conv.updated_at)}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={`max-w-[75%] px-4 py-3 rounded-xl text-sm leading-relaxed whitespace-pre-wrap break-words font-mono font-light text-[var(--accent)] animate-[msgIn_0.25s_ease-out] ${roleClasses[message.role]}`}>
      {message.content}
    </div>
  );
}
```

- [ ] **Step 2: Run frontend lint**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama/frontend && npm run lint`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/molecules/MessageBubble.tsx
git commit -m "feat: render /conversations list as clickable items in chat bubble"
```

---

### Task 4: Remove dead frontend code

**Files:**
- Modify: `frontend/src/providers/ChatProvider.tsx`
- Delete: `frontend/src/api/history.ts`
- Delete: `frontend/src/api/system.ts`
- Delete: `frontend/src/api/__tests__/history.test.ts`
- Modify: `frontend/src/hooks/__tests__/useChat.test.tsx`

- [ ] **Step 1: Remove `clearHistory` API dependency in `ChatProvider.tsx`**

Remove the import line:
```typescript
import { clearHistory as apiClearHistory } from '../api/history';
```

Replace the `clearHistory` callback (it currently calls `apiClearHistory()`):
```typescript
  const clearHistory = useCallback(async () => {
    setMessages([]);
    setConversationId(null);
  }, []);
```

- [ ] **Step 2: Delete dead API modules**

Delete these files:
- `frontend/src/api/history.ts`
- `frontend/src/api/system.ts`
- `frontend/src/api/__tests__/history.test.ts`

- [ ] **Step 3: Fix `useChat.test.tsx` — remove `/api/history` assertion**

In `frontend/src/hooks/__tests__/useChat.test.tsx`, rewrite the `clearHistory` test. The old test asserts a `DELETE /api/history` call. The new `clearHistory` just clears local state:

```typescript
  it('clearHistory empties messages', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ models: [], current: null }) });
    const { result } = renderHook(() => useChat(), { wrapper });
    await act(async () => { await result.current.clearHistory(); });
    expect(result.current.messages).toEqual([]);
  });
```

- [ ] **Step 4: Verify no dead imports remain**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama/frontend && grep -r "api/history\|api/system" src/`
Expected: No matches

- [ ] **Step 5: Run frontend lint and tests**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama/frontend && npm run lint && npx vitest run`
Expected: No lint errors, all tests pass

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/api/history.ts frontend/src/api/system.ts frontend/src/api/__tests__/history.test.ts frontend/src/providers/ChatProvider.tsx frontend/src/hooks/__tests__/useChat.test.tsx
git commit -m "chore: remove dead frontend code for /api/history and /api/system"
```

---

### Task 5: End-to-end verification

**Files:** None (testing only)

- [ ] **Step 1: Verify backend starts cleanly**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Verify frontend builds**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Verify frontend lints and tests pass**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama/frontend && npm run lint && npx vitest run`
Expected: No errors, all tests pass

- [ ] **Step 4: Verify no references to removed endpoints in frontend**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama/frontend && grep -rE "api/history|api/system|\"api/chat\"" src/`
Expected: No matches (only `api/chat/stream` and `api/chat/cancel` should remain)

- [ ] **Step 5: Verify no `_state` references in web API code**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && grep -n "_state" main.py | grep -v "_cli_state"`
Expected: Zero matches — all references should be `_cli_state`

- [ ] **Step 6: Manual smoke test**

Start the server and test:
1. Log in as user A, send a message — conversation created in DB
2. Log in as user B (different browser/incognito) — should see empty chat, NOT user A's history
3. Type `/conversations` — should see clickable conversation list
4. Click a conversation — should load that conversation's history
5. Select a different model — should not affect user A's model selection
