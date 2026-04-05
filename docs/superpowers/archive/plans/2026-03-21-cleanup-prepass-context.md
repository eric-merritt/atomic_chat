# Cleanup, Tool Pre-Pass, and Context Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove dead code, add a lightweight LLM pre-pass that dynamically selects tools per-turn, and wire conversation history into the chat pipeline.

**Architecture:** Three independent subsystems executed sequentially. Cleanup removes stale files and dead imports. The tool pre-pass uses qwen3:1.7b to select relevant tools from a compact index fetched from tools.eric-merritt.com at startup. The context pipeline loads current-conversation messages from Postgres and replays them as LangChain message types before each agent turn.

**Tech Stack:** Python 3, Flask, SQLAlchemy, LangChain, ChatOllama, Postgres (JSONB), httpx

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Delete | `index.py` | Dead RAG indexer |
| Delete | `index_repo.py` | Dead RAG indexer |
| Delete | `inspect_db.py` | Dead Chroma DB inspector |
| Delete | `run_agents.py` | Dead subagent launcher |
| Delete | `tools.py` (root) | Shadowed by `tools/` package |
| Delete | `agents/base.py` | Dead subagent code |
| Delete | `agents/codesearch.py` | Dead subagent code |
| Delete | `agents/dispatcher.py` | Dead subagent code |
| Delete | `agents/ecommerce.py` | Dead subagent code |
| Delete | `agents/filesystem.py` | Dead subagent code |
| Delete | `agents/web.py` | Dead subagent code |
| Delete | `agents/__init__.py` | Empty package init |
| Delete | `agents/continue.md` | Notes file |
| Modify | `config.py` | Remove `AGENT_PORTS`, `AGENT_MODELS`, `agent_url()`. Add `PREPASS_MODEL`. Keep `RATE_LIMITS`, `MAX_RETRIES`. |
| Modify | `main.py` | Remove dead import, add pre-pass + context pipeline |
| Modify | `tests/test_config.py` | Remove tests for deleted constants, add test for `PREPASS_MODEL` |
| Create | `prepass.py` | Tool pre-pass logic (compact index cache, LLM selection, fallback) |
| Create | `context.py` | Conversation history loading/saving, LangChain message replay |
| Create | `tests/test_prepass.py` | Tests for tool pre-pass |
| Create | `tests/test_context.py` | Tests for context pipeline |

---

### Task 1: Delete Stale Files

**Files:**
- Delete: `index.py`, `index_repo.py`, `inspect_db.py`, `run_agents.py`, `tools.py` (root)
- Delete: `agents/base.py`, `agents/codesearch.py`, `agents/dispatcher.py`, `agents/ecommerce.py`, `agents/filesystem.py`, `agents/web.py`, `agents/__init__.py`, `agents/continue.md`

- [ ] **Step 1: Delete all stale files**

```bash
rm index.py index_repo.py inspect_db.py run_agents.py tools.py
rm -r agents/
```

- [ ] **Step 2: Verify no remaining imports reference deleted files**

```bash
grep -rn "from agents" --include="*.py" . | grep -v __pycache__ | grep -v node_modules
grep -rn "import agents" --include="*.py" . | grep -v __pycache__ | grep -v node_modules
grep -rn "from run_agents" --include="*.py" . | grep -v __pycache__
grep -rn "from index" --include="*.py" . | grep -v __pycache__ | grep -v node_modules
grep -rn "from inspect_db" --include="*.py" . | grep -v __pycache__
```

Expected: No matches (all consumers were deleted files or dead code).

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "chore: remove dead files — agents/, index.py, run_agents.py, inspect_db.py, root tools.py"
```

---

### Task 2: Clean config.py

**Files:**
- Modify: `config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the updated test file**

Replace `tests/test_config.py` with:

```python
"""Test that config module exists and has required constants."""

import os


def test_config_rate_limits():
    from config import RATE_LIMITS
    assert isinstance(RATE_LIMITS, dict)
    assert "ebay" in RATE_LIMITS
    assert "amazon" in RATE_LIMITS
    assert "craigslist" in RATE_LIMITS
    assert "default" in RATE_LIMITS
    assert all(isinstance(v, (int, float)) for v in RATE_LIMITS.values())


def test_config_max_retries():
    from config import MAX_RETRIES
    assert isinstance(MAX_RETRIES, int)
    assert MAX_RETRIES >= 0


def test_config_prepass_model_default():
    from config import PREPASS_MODEL
    assert isinstance(PREPASS_MODEL, str)
    assert len(PREPASS_MODEL) > 0


def test_config_prepass_model_env_override(monkeypatch):
    monkeypatch.setenv("PREPASS_MODEL", "test-model:latest")
    # Re-import to pick up env var
    import importlib
    import config
    importlib.reload(config)
    assert config.PREPASS_MODEL == "test-model:latest"
    # Restore
    monkeypatch.delenv("PREPASS_MODEL")
    importlib.reload(config)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: `test_config_prepass_model_default` FAILS (PREPASS_MODEL not yet defined). Old tests for AGENT_PORTS still pass (not yet removed from config).

- [ ] **Step 3: Update config.py**

Replace entire `config.py` with:

```python
"""Central configuration."""

import os

# Pre-pass model for dynamic tool selection
PREPASS_MODEL = os.environ.get("PREPASS_MODEL", "qwen3:1.7b")

# Seconds between requests to the same platform
RATE_LIMITS = {
    "ebay": 6,
    "amazon": 6,
    "craigslist": 6,
    "default": 6,
}

# Dispatcher retry config
MAX_RETRIES = 2
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Remove dead import from main.py**

In `main.py`, delete line 19:

```python
# DELETE THIS LINE:
from config import AGENT_PORTS, agent_url
```

- [ ] **Step 6: Verify main.py still imports cleanly**

Run: `.venv/bin/python -c "import main"`
Expected: No ImportError.

- [ ] **Step 7: Commit**

```bash
git add config.py tests/test_config.py main.py
git commit -m "chore: clean config.py — remove AGENT_PORTS/AGENT_MODELS/agent_url, add PREPASS_MODEL"
```

---

### Task 3: Build the Tool Pre-Pass Module

**Files:**
- Create: `prepass.py`
- Create: `tests/test_prepass.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prepass.py`:

```python
"""Tests for tool pre-pass module."""

import json
import pytest


# --- Compact index ---

def test_build_compact_index():
    """Compact index extracts name + first line of description."""
    from prepass import _build_compact_index

    full_tools = [
        {"name": "read", "description": "Read a file and return its contents.\nSupports text and binary.", "params": {}},
        {"name": "web_search", "description": "Search the web using DuckDuckGo", "params": {}},
    ]
    index = _build_compact_index(full_tools)
    assert index == {
        "read": "Read a file and return its contents.",
        "web_search": "Search the web using DuckDuckGo",
    }


def test_build_compact_index_empty():
    from prepass import _build_compact_index
    assert _build_compact_index([]) == {}


def test_build_compact_index_missing_description():
    from prepass import _build_compact_index
    tools = [{"name": "foo", "description": "", "params": {}}]
    index = _build_compact_index(tools)
    assert index == {"foo": ""}


# --- Pre-pass prompt ---

def test_build_prepass_prompt():
    from prepass import _build_prepass_prompt

    index = {"read": "Read a file", "web_search": "Search the web"}
    prompt = _build_prepass_prompt("find me a recipe", index)
    assert "find me a recipe" in prompt
    assert "read: Read a file" in prompt
    assert "web_search: Search the web" in prompt
    assert "JSON array" in prompt


# --- Parse pre-pass response ---

def test_parse_prepass_response_valid():
    from prepass import _parse_prepass_response
    known = {"read", "web_search", "ls"}
    result = _parse_prepass_response('["read", "web_search"]', known)
    assert result == ["read", "web_search"]


def test_parse_prepass_response_filters_unknown():
    from prepass import _parse_prepass_response
    known = {"read", "ls"}
    result = _parse_prepass_response('["read", "nonexistent"]', known)
    assert result == ["read"]


def test_parse_prepass_response_malformed_returns_none():
    from prepass import _parse_prepass_response
    result = _parse_prepass_response("not json at all", {"read"})
    assert result is None


def test_parse_prepass_response_empty_returns_none():
    from prepass import _parse_prepass_response
    result = _parse_prepass_response("[]", {"read"})
    assert result is None


def test_parse_prepass_response_all_unknown_returns_none():
    from prepass import _parse_prepass_response
    result = _parse_prepass_response('["fake1", "fake2"]', {"read"})
    assert result is None


def test_parse_prepass_response_strips_think_tags():
    """qwen3 models wrap output in <think>...</think> tags."""
    from prepass import _parse_prepass_response
    known = {"read", "web_search"}
    raw = '<think>\nThe user wants to read a file.\n</think>\n["read"]'
    result = _parse_prepass_response(raw, known)
    assert result == ["read"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_prepass.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'prepass'`

- [ ] **Step 3: Implement prepass.py**

Create `prepass.py`:

```python
"""Tool pre-pass: lightweight LLM selects relevant tools per-turn.

Flow:
  1. At startup, fetch full tool list from tools.eric-merritt.com
  2. Build compact index (name → first-line description)
  3. Each turn, ask PREPASS_MODEL which tools are needed
  4. Return list of tool names; caller fetches full schemas and binds them
"""

import json
import logging
import re

import httpx
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

from config import PREPASS_MODEL

logger = logging.getLogger(__name__)

TOOLS_SERVER_URL = "https://tools.eric-merritt.com"

# Module-level cache
_compact_index: dict[str, str] | None = None
_known_tool_names: set[str] | None = None


def _build_compact_index(full_tools: list[dict]) -> dict[str, str]:
    """Strip full tool list down to {name: first_line_of_description}."""
    index = {}
    for t in full_tools:
        desc = t.get("description", "")
        first_line = desc.split("\n")[0].strip() if desc else ""
        index[t["name"]] = first_line
    return index


def _build_prepass_prompt(user_message: str, index: dict[str, str]) -> str:
    """Build the prompt sent to the pre-pass model."""
    tool_lines = "\n".join(f"- {name}: {desc}" for name, desc in index.items())
    return f"""Given the user's request, select which tools are needed.
Return ONLY a JSON array of tool names. Select the minimum set needed.

Available tools:
{tool_lines}

User request: "{user_message}"
"""


def _parse_prepass_response(raw: str, known_names: set[str]) -> list[str] | None:
    """Parse the pre-pass model's response into a validated tool name list.

    Returns None if the response is malformed, empty, or contains no valid names.
    """
    # Strip <think>...</think> tags (qwen3 models)
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Extract JSON array from response (may have surrounding text)
    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if not match:
        return None

    try:
        parsed = json.loads(match.group())
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(parsed, list):
        return None

    # Filter to known tool names
    valid = [name for name in parsed if isinstance(name, str) and name in known_names]

    return valid if valid else None


def load_tool_index() -> dict[str, str]:
    """Fetch tool list from tools server and cache compact index.

    Call once at startup. Returns the compact index {name: first_line_description}.
    Raises on network failure — caller should handle gracefully.
    """
    global _compact_index, _known_tool_names

    resp = httpx.get(f"{TOOLS_SERVER_URL}/", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    full_tools = data.get("tools", [])

    _compact_index = _build_compact_index(full_tools)
    _known_tool_names = set(_compact_index.keys())

    logger.info("Tool index loaded: %d tools", len(_compact_index))
    return _compact_index


def select_tools(user_message: str, fallback_names: list[str]) -> list[str]:
    """Run the pre-pass model to select tools for this turn.

    Args:
        user_message: The user's current message.
        fallback_names: Tool names to use if pre-pass fails.

    Returns:
        List of tool name strings.
    """
    global _compact_index, _known_tool_names

    if _compact_index is None or _known_tool_names is None:
        logger.warning("Tool index not loaded, using fallback")
        return fallback_names

    prompt = _build_prepass_prompt(user_message, _compact_index)

    try:
        llm = ChatOllama(
            model=PREPASS_MODEL,
            temperature=0,
            base_url="http://localhost:11434",
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        result = _parse_prepass_response(response.content, _known_tool_names)

        if result is None:
            logger.warning("Pre-pass returned no valid tools, using fallback")
            return fallback_names

        logger.info("Pre-pass selected %d tools: %s", len(result), result)
        return result

    except Exception as e:
        logger.warning("Pre-pass failed (%s), using fallback", e)
        return fallback_names
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_prepass.py -v`
Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add prepass.py tests/test_prepass.py
git commit -m "feat: add tool pre-pass module — lightweight LLM selects tools per-turn"
```

---

### Task 4: Build the Context Pipeline Module

**Files:**
- Create: `context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_context.py`:

```python
"""Tests for context pipeline module."""

import json
import pytest


# --- Message replay ---

def test_replay_user_message():
    from context import _db_row_to_langchain
    from langchain_core.messages import HumanMessage

    row = {"role": "user", "content": "hello", "tool_calls": []}
    msg = _db_row_to_langchain(row)
    assert isinstance(msg, HumanMessage)
    assert msg.content == "hello"


def test_replay_assistant_text():
    from context import _db_row_to_langchain
    from langchain_core.messages import AIMessage

    row = {"role": "assistant", "content": "hi there", "tool_calls": []}
    msg = _db_row_to_langchain(row)
    assert isinstance(msg, AIMessage)
    assert msg.content == "hi there"
    assert not msg.tool_calls


def test_replay_assistant_tool_call():
    from context import _db_row_to_langchain
    from langchain_core.messages import AIMessage

    row = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"name": "read", "args": {"path": "/tmp/test"}, "id": "call_1"}],
    }
    msg = _db_row_to_langchain(row)
    assert isinstance(msg, AIMessage)
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0]["name"] == "read"


def test_replay_tool_result():
    from context import _db_row_to_langchain
    from langchain_core.messages import ToolMessage

    row = {
        "role": "tool",
        "content": '{"status": "success", "data": "file contents"}',
        "tool_calls": [{"name": "read", "id": "call_1"}],
    }
    msg = _db_row_to_langchain(row)
    assert isinstance(msg, ToolMessage)
    assert msg.name == "read"
    assert msg.tool_call_id == "call_1"


# --- Truncation ---

def test_tool_result_truncation():
    from context import _db_row_to_langchain

    long_content = "x" * 5000
    row = {"role": "tool", "content": long_content, "tool_calls": [{"name": "web_search", "id": "call_2"}]}
    msg = _db_row_to_langchain(row)
    assert len(msg.content) <= 4000


# --- Build history ---

def test_build_history_ordering():
    from context import build_history
    from langchain_core.messages import HumanMessage, AIMessage

    db_messages = [
        {"role": "user", "content": "first", "tool_calls": []},
        {"role": "assistant", "content": "response1", "tool_calls": []},
        {"role": "user", "content": "second", "tool_calls": []},
    ]
    history = build_history(db_messages)
    assert len(history) == 3
    assert isinstance(history[0], HumanMessage)
    assert history[0].content == "first"
    assert isinstance(history[1], AIMessage)
    assert isinstance(history[2], HumanMessage)
    assert history[2].content == "second"


def test_build_history_empty():
    from context import build_history
    assert build_history([]) == []


# --- Serialization for DB ---

def test_serialize_user_message():
    from context import serialize_user_message

    row = serialize_user_message("what is 2+2")
    assert row["role"] == "user"
    assert row["content"] == "what is 2+2"
    assert row["tool_calls"] == []


def test_serialize_assistant_text():
    from context import serialize_assistant_message

    row = serialize_assistant_message("The answer is 4", tool_calls=[])
    assert row["role"] == "assistant"
    assert row["content"] == "The answer is 4"
    assert row["tool_calls"] == []


def test_serialize_assistant_tool_call():
    from context import serialize_assistant_message

    calls = [{"name": "read", "args": {"path": "/tmp"}, "id": "call_1"}]
    row = serialize_assistant_message("", tool_calls=calls)
    assert row["role"] == "assistant"
    assert row["content"] == ""
    assert len(row["tool_calls"]) == 1


def test_serialize_tool_result():
    from context import serialize_tool_result

    row = serialize_tool_result("read", "call_1", '{"status": "success", "data": "contents"}')
    assert row["role"] == "tool"
    assert row["content"] == '{"status": "success", "data": "contents"}'
    assert row["tool_calls"] == [{"name": "read", "id": "call_1"}]


def test_serialize_tool_result_truncates():
    from context import serialize_tool_result

    long = "y" * 5000
    row = serialize_tool_result("web_search", "call_2", long)
    assert len(row["content"]) <= 4000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'context'`

- [ ] **Step 3: Implement context.py**

Create `context.py`:

```python
"""Context pipeline: conversation history loading, replay, and persistence.

Converts between DB rows (dicts with role/content/tool_calls) and
LangChain message types for agent consumption.
"""

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
)

TOOL_RESULT_MAX_CHARS = 4000


def _db_row_to_langchain(row: dict):
    """Convert a DB message dict to the corresponding LangChain message.

    Args:
        row: Dict with keys: role, content, tool_calls.

    Returns:
        HumanMessage, AIMessage, or ToolMessage.
    """
    role = row["role"]
    content = row.get("content", "")
    tool_calls = row.get("tool_calls", [])

    if role == "user":
        return HumanMessage(content=content)

    if role == "assistant":
        if tool_calls:
            return AIMessage(content=content, tool_calls=tool_calls)
        return AIMessage(content=content)

    if role == "tool":
        truncated = content[:TOOL_RESULT_MAX_CHARS] if content else ""
        tool_name = tool_calls[0]["name"] if tool_calls else "unknown"
        tool_call_id = tool_calls[0].get("id", "unknown") if tool_calls else "unknown"
        return ToolMessage(content=truncated, name=tool_name, tool_call_id=tool_call_id)

    # Fallback — treat unknown roles as human messages
    return HumanMessage(content=content)


def build_history(db_messages: list[dict]) -> list:
    """Convert a list of DB message dicts to LangChain messages.

    Args:
        db_messages: List of dicts from ConversationMessage table,
                     ordered by created_at ascending.

    Returns:
        List of LangChain message objects.
    """
    return [_db_row_to_langchain(row) for row in db_messages]


# --- Serialization helpers (LangChain → DB row dicts) ---

def serialize_user_message(content: str) -> dict:
    """Serialize a user message for DB storage."""
    return {"role": "user", "content": content, "tool_calls": []}


def serialize_assistant_message(content: str, tool_calls: list) -> dict:
    """Serialize an assistant message for DB storage."""
    return {"role": "assistant", "content": content, "tool_calls": tool_calls or []}


def serialize_tool_result(tool_name: str, tool_call_id: str, content: str) -> dict:
    """Serialize a tool result for DB storage. Truncates content to 4000 chars."""
    truncated = content[:TOOL_RESULT_MAX_CHARS] if content else ""
    return {
        "role": "tool",
        "content": truncated,
        "tool_calls": [{"name": tool_name, "id": tool_call_id}],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_context.py -v`
Expected: All 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add context.py tests/test_context.py
git commit -m "feat: add context pipeline — conversation history replay and serialization"
```

---

### Task 5: Wire Pre-Pass Into main.py

**Files:**
- Modify: `main.py:19,121-124,169-183,189-260`
- Create: `tests/test_prepass_integration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_prepass_integration.py`:

```python
"""Integration test: pre-pass fallback when tool index isn't loaded."""

def test_select_tools_fallback_without_index():
    """select_tools returns fallback when index hasn't been loaded."""
    from prepass import select_tools

    fallback = ["read", "ls", "write"]
    result = select_tools("do something", fallback)
    assert result == fallback
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_prepass_integration.py -v`
Expected: PASS (fallback path works without network).

- [ ] **Step 3: Update main.py — imports and tool index loading**

At the top of `main.py`:
1. Delete the dead import: `from config import AGENT_PORTS, agent_url`
2. After `from tools import ALL_TOOLS`, add:

```python
from prepass import load_tool_index, select_tools
from context import build_history, serialize_user_message, serialize_assistant_message, serialize_tool_result
from auth.conversations import Conversation, ConversationMessage
```

3. Add `import logging` and `from datetime import datetime, timezone` at module level (these are used later in `chat_stream` — keep them at module level, not inline).

4. After the existing `init_db()` block (line 143), add the tool index loader:

```python
# Load compact tool index from tools server at startup
with app.app_context():
    try:
        load_tool_index()
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to load tool index at startup: %s", e)
```

- [ ] **Step 4: Update _build_agent to accept tool names instead of indices**

Replace the `_build_agent` function with:

```python
# Build lookup dict for fetching tools by name
_TOOL_BY_NAME = {t.name: t for t in ALL_TOOLS}

# Per-conversation cache: conversation_id → last tool names used
_last_tool_selection: dict[str, list[str]] = {}
_last_agent_cache: dict[str, object] = {}


def _build_agent(model_name: str, tool_names: list[str], conversation_id: str | None = None):
    """Build a LangChain agent with only the specified tools bound.

    Caches per conversation_id. If tool_names match the previous turn's
    selection for this conversation, returns the cached agent.

    Args:
        model_name: Ollama model name.
        tool_names: List of tool name strings to bind.
        conversation_id: Optional conversation ID for caching.
    """
    if conversation_id and conversation_id in _last_tool_selection:
        if sorted(_last_tool_selection[conversation_id]) == sorted(tool_names):
            cached = _last_agent_cache.get(conversation_id)
            if cached is not None:
                return cached

    llm = ChatOllama(
        model=model_name,
        temperature=0,
        base_url="http://localhost:11434",
    ).bind(response_format=ResponseFormat.JSON)

    tools = [_TOOL_BY_NAME[name] for name in tool_names if name in _TOOL_BY_NAME]

    agent = create_agent(
        llm,
        tools,
        system_prompt=SYSTEM_PROMPT,
        response_format=ResponseFormat.JSON,
    )

    if conversation_id:
        _last_tool_selection[conversation_id] = tool_names
        _last_agent_cache[conversation_id] = agent

    return agent
```

- [ ] **Step 5: Update DEFAULT_TOOL_NAMES to be a list**

Replace lines 123-124:

```python
DEFAULT_TOOL_NAMES = ["read", "info", "ls", "tree", "write", "append", "replace", "insert",
                      "delete", "copy", "move", "mkdir", "grep", "find", "definition",
                      "webscrape", "find_all", "find_download_link"]
```

Remove `DEFAULT_TOOL_INDICES` entirely.

- [ ] **Step 6: Update _get_user_selected_tools to return names**

Replace `_get_user_selected_tools`:

```python
def _get_user_selected_tools() -> list[str]:
    """Get selected tool names for the current user, falling back to defaults."""
    if hasattr(current_user, 'preferences') and current_user.preferences:
        user_tools = current_user.preferences.get("selected_tools")
        if user_tools is not None:
            # Convert indices to names if user still has old index-based prefs
            if user_tools and isinstance(user_tools[0], int):
                return [ALL_TOOLS[i].name for i in user_tools if i < len(ALL_TOOLS)]
            return user_tools
    return list(DEFAULT_TOOL_NAMES)
```

- [ ] **Step 7: Verify imports are clean**

Run: `.venv/bin/python -c "import main"`
Expected: No ImportError (tool index load may warn if tools server is unreachable — that's fine).

- [ ] **Step 8: Commit**

```bash
git add main.py tests/test_prepass_integration.py
git commit -m "feat: wire tool pre-pass into main.py — dynamic tool selection per-turn"
```

---

### Task 6: Wire Context Pipeline Into chat_stream

**Files:**
- Modify: `main.py:189-260` (the `chat_stream` function)

- [ ] **Step 1: Update chat_stream to accept conversation_id and load history**

Note: `Conversation`, `ConversationMessage`, `logging`, and `datetime` imports were already added at module level in Task 5 Step 3. Do NOT add inline imports inside the generator.

Replace the entire `chat_stream` function with:

```python
@app.route("/api/chat/stream", methods=["POST"])
@login_required
def chat_stream():
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    conversation_id = data.get("conversation_id")

    if not user_msg:
        return jsonify({"error": "message required"}), 400

    prefs = current_user.preferences or {}
    model_name = prefs.get("model")

    if not model_name:
        return jsonify({"error": "No model selected"}), 400

    db = get_db()

    # --- Conversation management ---
    if conversation_id:
        conv = db.query(Conversation).filter_by(
            id=conversation_id, user_id=current_user.id
        ).first()
        if not conv:
            return jsonify({"error": "Conversation not found"}), 404
    else:
        conv = Conversation(
            user_id=current_user.id,
            title=user_msg[:60],
            model=model_name,
        )
        db.add(conv)
        db.commit()
        conversation_id = conv.id

    # --- Load conversation history ---
    db_messages = (
        db.query(ConversationMessage)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationMessage.created_at.asc())
        .all()
    )
    history_rows = [
        {"role": m.role, "content": m.content, "tool_calls": m.tool_calls or []}
        for m in db_messages
    ]
    history = build_history(history_rows)

    # --- Tool pre-pass ---
    fallback_names = _get_user_selected_tools()
    tool_names = select_tools(user_msg, fallback_names)

    agent = _build_agent(model_name, tool_names, conversation_id)

    # --- Assemble messages ---
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content="Respond ONLY with valid JSON when calling tools."),
    ] + history + [
        HumanMessage(content=user_msg),
    ]

    def generate():
        full_response = ""
        # Collect messages in order as (type, data) tuples to preserve
        # correct tool_call → tool_result interleaving for DB persistence
        ordered_messages = []

        # Send conversation_id first so frontend can track it
        yield json.dumps({"conversation_id": conversation_id}) + "\n"

        try:
            for event in agent.stream({"messages": messages}, stream_mode="updates"):
                for node_output in event.values():
                    for msg in node_output.get("messages", []):
                        # Tool calls — LangChain ToolCall is a TypedDict, use dict access
                        if getattr(msg, "tool_calls", None):
                            for call in msg.tool_calls:
                                ordered_messages.append(("tool_call", {
                                    "name": call["name"],
                                    "args": call["args"],
                                    "id": call.get("id", ""),
                                }))
                                yield json.dumps({
                                    "tool_call": {
                                        "tool": call["name"],
                                        "input": str(call["args"])
                                    }
                                }) + "\n"

                        # Tool results
                        elif isinstance(msg, ToolMessage):
                            ordered_messages.append(("tool_result", {
                                "name": msg.name,
                                "tool_call_id": getattr(msg, "tool_call_id", ""),
                                "content": str(msg.content),
                            }))
                            yield json.dumps({
                                "tool_result": {
                                    "tool": msg.name,
                                    "output": str(msg.content)[:500]
                                }
                            }) + "\n"

                        # Normal text
                        elif msg.content:
                            full_response += msg.content
                            yield json.dumps({"chunk": msg.content}) + "\n"

        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        # --- Persist messages to DB (in correct order) ---
        try:
            # Save user message
            user_row = serialize_user_message(user_msg)
            db.add(ConversationMessage(
                conversation_id=conversation_id,
                role=user_row["role"],
                content=user_row["content"],
                tool_calls=user_row["tool_calls"],
            ))

            # Save tool calls and results in the order they occurred
            for msg_type, msg_data in ordered_messages:
                if msg_type == "tool_call":
                    db.add(ConversationMessage(
                        conversation_id=conversation_id,
                        role="assistant",
                        content="",
                        tool_calls=[msg_data],
                    ))
                elif msg_type == "tool_result":
                    result_row = serialize_tool_result(
                        msg_data["name"], msg_data["tool_call_id"], msg_data["content"]
                    )
                    db.add(ConversationMessage(
                        conversation_id=conversation_id,
                        role=result_row["role"],
                        content=result_row["content"],
                        tool_calls=result_row["tool_calls"],
                    ))

            # Save assistant response
            if full_response:
                asst_row = serialize_assistant_message(full_response, tool_calls=[])
                db.add(ConversationMessage(
                    conversation_id=conversation_id,
                    role=asst_row["role"],
                    content=asst_row["content"],
                    tool_calls=asst_row["tool_calls"],
                ))

            conv.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as e:
            logging.getLogger(__name__).error("Failed to persist messages: %s", e)

        yield json.dumps({
            "done": True,
            "full_response": full_response,
            "conversation_id": conversation_id,
        }) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 2: Verify main.py imports cleanly**

Run: `.venv/bin/python -c "import main"`
Expected: No ImportError.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: wire context pipeline into chat_stream — history loading, message persistence, conversation_id flow"
```

---

### Task 7: Verify Frontend conversation_id Handling

**Files:**
- Verify: `frontend/src/api/chat.ts` (already sends `conversation_id`)

The frontend already sends `conversation_id` in the request body via `streamChatAsync()` in `frontend/src/api/chat.ts`. The only change needed is to handle the new `conversation_id` line in the NDJSON response stream.

- [ ] **Step 1: Verify the existing frontend chat API**

```bash
cat frontend/src/api/chat.ts
```

Confirm it already sends `conversation_id` in the request body. It should — `streamChatAsync(message, conversationId?)` already passes `conversation_id: conversationId` in the JSON body.

- [ ] **Step 2: Check if the stream parser handles the conversation_id event**

```bash
grep -rn "conversation_id" frontend/src/ --include="*.ts" --include="*.tsx"
```

If the stream parser in `atoms/stream.ts` or `hooks/useStream.ts` doesn't handle the `conversation_id` NDJSON line, add a case for it. The first line of the response is now `{"conversation_id": "..."}` — the parser should extract and surface this to `ChatProvider`.

- [ ] **Step 3: If changes needed, implement and commit**

```bash
git add frontend/src/
git commit -m "feat: frontend handles conversation_id from NDJSON response stream"
```

If no changes needed, skip this commit.

---

### Task 8: End-to-End Verification

- [ ] **Step 1: Run all tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Start the server and verify basic chat flow**

```bash
.venv/bin/python main.py --serve
```

Verify in the browser:
1. Send a message — response streams back with a `conversation_id` in the first NDJSON line
2. Send a follow-up — the same `conversation_id` is sent, history is loaded
3. Check the database — `conversation_messages` table has the user messages, assistant responses, and any tool call/result pairs

- [ ] **Step 3: Verify pre-pass fallback**

Stop `tools_server.py` (or ensure it's not running). Send a message. The pre-pass should log a warning and fall back to `DEFAULT_TOOL_NAMES`. Chat should still work.

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address issues found during end-to-end verification"
```
