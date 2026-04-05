# Task-Aware Tool Curation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blind prepass with a two-agent pipeline (Task Extractor + Tool Curator) backed by a `conversation_tasks` table and a static workflow group registry, with frontend recommendation chips for user approval.

**Architecture:** Two sequential 1.7B Ollama workers per chat turn. Task Extractor reads messages and writes tasks to the DB. Tool Curator reads tasks and either passes through or recommends workflow groups. Frontend shows accept/dismiss chip when recommendations exist. Short-circuit: no new tasks = no curator inference.

**Tech Stack:** Python/Flask, SQLAlchemy, Alembic, Ollama (qwen3:1.7b), React/TypeScript, Tailwind CSS

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `workflow_groups.py` | Create | WorkflowGroup dataclass + static registry |
| `tests/test_workflow_groups.py` | Create | Registry validation tests |
| `auth/conversation_tasks.py` | Create | ConversationTask SQLAlchemy model |
| `alembic/versions/*_add_conversation_tasks.py` | Create | DB migration |
| `tests/test_conversation_tasks.py` | Create | Model CRUD tests |
| `task_extractor.py` | Create | 1.7B #1 — extract tasks from messages |
| `tests/test_task_extractor.py` | Create | Prompt building + response parsing tests |
| `tool_curator.py` | Create | 1.7B #2 — recommend workflow groups |
| `tests/test_tool_curator.py` | Create | Curation logic + short-circuit tests |
| `main.py` | Modify | Replace prepass with new pipeline |
| `config.py` | Modify | Add model config keys |
| `prepass.py` | Delete | Replaced by new pipeline |
| `frontend/src/atoms/stream.ts` | Modify | Add recommendation event type |
| `frontend/src/api/chat.ts` | Modify | Add recommend response API call |
| `frontend/src/providers/ChatProvider.tsx` | Modify | Handle recommendation flow |
| `frontend/src/components/organisms/InputBar.tsx` | Modify | Recommendation chip UI |

---

## Task 1: Workflow Group Registry

**Files:**
- Create: `workflow_groups.py`
- Create: `tests/test_workflow_groups.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_groups.py
from workflow_groups import WORKFLOW_GROUPS, WorkflowGroup


def test_registry_is_not_empty():
    assert len(WORKFLOW_GROUPS) > 0


def test_all_entries_are_workflow_groups():
    for name, group in WORKFLOW_GROUPS.items():
        assert isinstance(group, WorkflowGroup), f"{name} is not a WorkflowGroup"
        assert isinstance(group.tools, list)
        assert len(group.tools) > 0, f"{name} has no tools"
        assert isinstance(group.tooltip, str)
        assert len(group.tooltip) > 0, f"{name} has no tooltip"


def test_no_duplicate_tools_across_groups():
    seen = {}
    for name, group in WORKFLOW_GROUPS.items():
        for tool in group.tools:
            assert tool not in seen, f"Tool '{tool}' in both '{seen[tool]}' and '{name}'"
            seen[tool] = name


def test_all_tools_exist_in_registry():
    from tools import ALL_TOOLS
    all_names = {t.name for t in ALL_TOOLS}
    for name, group in WORKFLOW_GROUPS.items():
        for tool in group.tools:
            assert tool in all_names, f"Tool '{tool}' in group '{name}' not found in ALL_TOOLS"


def test_tooltip_is_concise():
    for name, group in WORKFLOW_GROUPS.items():
        word_count = len(group.tooltip.split())
        assert word_count <= 15, f"{name} tooltip is {word_count} words (max 15)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_workflow_groups.py -v`
Expected: FAIL with "No module named 'workflow_groups'"

- [ ] **Step 3: Write the implementation**

```python
# workflow_groups.py
"""Static registry of workflow groups for tool curation.

Each group maps a human-readable name to a list of tool names and a short
tooltip. The Tool Curator recommends groups — not individual tools.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowGroup:
    tools: list[str]
    tooltip: str


WORKFLOW_GROUPS: dict[str, WorkflowGroup] = {
    "Filesystem": WorkflowGroup(
        tools=["read", "info", "ls", "tree", "write", "append",
               "replace", "insert", "delete", "copy", "move", "mkdir"],
        tooltip="File reading, writing, and directory operations",
    ),
    "Code Search": WorkflowGroup(
        tools=["grep", "find", "definition"],
        tooltip="Search code by pattern, filename, or symbol",
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
    "OnlyFans": WorkflowGroup(
        tools=["of_search_creators", "of_creator_profile", "of_creator_media",
               "of_subscribe", "of_message_creator", "of_earnings_report"],
        tooltip="Creator discovery, profiles, and media management",
    ),
    "Torrent": WorkflowGroup(
        tools=["torrent_search", "torrent_details", "torrent_download",
               "torrent_status", "torrent_remove", "torrent_list"],
        tooltip="Torrent search, download, and management",
    ),
    "Accounting": WorkflowGroup(
        tools=["create_ledger", "list_accounts", "create_account",
               "update_account", "deactivate_account",
               "journalize_transaction", "search_journal", "void_entry",
               "account_ledger", "register_item", "receive_inventory",
               "adjust_inventory", "item_history", "fifo_cost",
               "lifo_cost", "inventory_valuation", "close_period",
               "trial_balance", "income_statement", "balance_sheet",
               "period_activity"],
        tooltip="Double-entry bookkeeping and financial reports",
    ),
}


def tools_for_groups(group_names: list[str]) -> list[str]:
    """Return flat list of tool names for the given group names."""
    tools = []
    for name in group_names:
        group = WORKFLOW_GROUPS.get(name)
        if group:
            tools.extend(group.tools)
    return tools


def group_for_tool(tool_name: str) -> str | None:
    """Return the group name a tool belongs to, or None."""
    for name, group in WORKFLOW_GROUPS.items():
        if tool_name in group.tools:
            return name
    return None
```

**Note:** The tool names in each group must exactly match `t.name` from the corresponding tools module. Before writing this file, verify tool names by running:
```bash
python -c "from tools import ALL_TOOLS; [print(t.name) for t in ALL_TOOLS]"
```
Update the lists above to match actual names.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_workflow_groups.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add workflow_groups.py tests/test_workflow_groups.py
git commit -m "feat: add workflow group registry for tool curation"
```

---

## Task 2: ConversationTask Model + Migration

**Files:**
- Create: `auth/conversation_tasks.py`
- Modify: `main.py` (import to register model with Base)
- Create: `alembic/versions/*_add_conversation_tasks.py`
- Create: `tests/test_conversation_tasks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_conversation_tasks.py
"""Tests for ConversationTask model CRUD."""
import pytest
from datetime import datetime, timezone
from auth.conversation_tasks import ConversationTask


def test_conversation_task_fields():
    """Verify the model has the expected columns."""
    columns = {c.name for c in ConversationTask.__table__.columns}
    assert columns == {"id", "conversation_id", "message_id", "title", "status", "created_at"}


def test_default_status():
    task = ConversationTask(title="test task", conversation_id="fake-id")
    assert task.status == "pending"


def test_status_values():
    """Status must be one of the allowed values."""
    for status in ("pending", "active", "done"):
        task = ConversationTask(title="t", conversation_id="x", status=status)
        assert task.status == status
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_conversation_tasks.py -v`
Expected: FAIL with "No module named 'auth.conversation_tasks'"

- [ ] **Step 3: Write the model**

```python
# auth/conversation_tasks.py
"""SQLAlchemy model for conversation-scoped tasks.

These tasks are ephemeral pipeline artifacts created by the Task Extractor
and consumed by the Tool Curator. They die with the conversation.

When the PM workflow lands, conversation tasks can be promoted to
project_tasks via a one-way copy with a promoted_from FK.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from auth.models import Base, _uuid, _now


class ConversationTask(Base):
    __tablename__ = "conversation_tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id = Column(
        String(36),
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), default=_now)

    conversation = relationship("Conversation")
```

- [ ] **Step 4: Register the model import in main.py**

Add this line next to the existing `import auth.conversations` in main.py:

```python
import auth.conversation_tasks  # register ConversationTask with Base
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_conversation_tasks.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Generate the Alembic migration**

Run: `alembic revision --autogenerate -m "add conversation_tasks table"`

Verify the generated migration contains:
- `op.create_table('conversation_tasks', ...)` with all 6 columns
- Index on `conversation_id`
- ForeignKey constraints to `conversations` and `conversation_messages`

- [ ] **Step 7: Apply the migration**

Run: `alembic upgrade head`

- [ ] **Step 8: Commit**

```bash
git add auth/conversation_tasks.py tests/test_conversation_tasks.py alembic/versions/*_add_conversation_tasks.py main.py
git commit -m "feat: add ConversationTask model and migration"
```

---

## Task 3: Task Extractor

**Files:**
- Create: `task_extractor.py`
- Create: `tests/test_task_extractor.py`
- Modify: `config.py`

- [ ] **Step 1: Add config key**

In `config.py`, add (note: `config.py` uses `os`, not `_os`):

```python
TASK_EXTRACTOR_MODEL = os.environ.get("TASK_EXTRACTOR_MODEL", "qwen3:1.7b")
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_task_extractor.py
"""Tests for Task Extractor prompt building and response parsing."""
from task_extractor import _build_extractor_prompt, _parse_extractor_response


class TestBuildPrompt:
    def test_includes_user_message(self):
        prompt = _build_extractor_prompt("scrape the site", [], [])
        assert "scrape the site" in prompt

    def test_includes_existing_tasks(self):
        tasks = [{"title": "existing task", "status": "pending"}]
        prompt = _build_extractor_prompt("do more", tasks, [])
        assert "existing task" in prompt

    def test_includes_recent_messages(self):
        history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        prompt = _build_extractor_prompt("next step", [], history)
        assert "hello" in prompt

    def test_empty_tasks_shows_none(self):
        prompt = _build_extractor_prompt("hi", [], [])
        assert "(none)" in prompt


class TestParseResponse:
    def test_valid_array(self):
        result = _parse_extractor_response('["task one", "task two"]')
        assert result == ["task one", "task two"]

    def test_empty_array(self):
        result = _parse_extractor_response('[]')
        assert result == []

    def test_with_think_tags(self):
        raw = '<think>hmm let me think</think>["scrape URL"]'
        result = _parse_extractor_response(raw)
        assert result == ["scrape URL"]

    def test_malformed_returns_empty(self):
        result = _parse_extractor_response("I don't understand")
        assert result == []

    def test_non_string_items_filtered(self):
        result = _parse_extractor_response('[123, "valid task", null]')
        assert result == ["valid task"]

    def test_json_in_surrounding_text(self):
        raw = 'Here are the tasks: ["task A"] hope that helps'
        result = _parse_extractor_response(raw)
        assert result == ["task A"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_task_extractor.py -v`
Expected: FAIL with "No module named 'task_extractor'"

- [ ] **Step 4: Write the implementation**

```python
# task_extractor.py
"""Task Extractor — 1.7B worker #1.

Reads the user's message and recent conversation history, extracts new
tasks, and writes them to conversation_tasks. Signals whether new tasks
were found so the Tool Curator can short-circuit.
"""

import json
import logging
import re

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

from config import TASK_EXTRACTOR_MODEL

logger = logging.getLogger(__name__)


def _build_extractor_prompt(
    user_message: str,
    existing_tasks: list[dict],
    recent_messages: list[dict],
) -> str:
    """Build the prompt for the Task Extractor model."""
    if existing_tasks:
        task_lines = "\n".join(
            f"- [{t['status']}] {t['title']}" for t in existing_tasks
        )
    else:
        task_lines = "(none)"

    if recent_messages:
        history_lines = "\n".join(
            f"{m['role']}: {m['content'][:200]}" for m in recent_messages[-5:]
        )
    else:
        history_lines = "(none)"

    return f"""You are a task extraction agent. Read the user's message and conversation
context, then decide if there are new tasks.

Current tasks:
{task_lines}

Recent conversation:
{history_lines}

User message: "{user_message}"

Rules:
- A "task" is a concrete action the user wants the agent to perform.
- Follow-ups like "try again", "format that differently", "now do X with that"
  are NOT new tasks — they modify existing tasks.
- If the message contains new tasks, return a JSON array of short task titles.
- If there are no new tasks, return an empty array.

Return ONLY a JSON array. Examples:
- New tasks: ["Scrape supplier pricing from URL", "Import prices into ledger"]
- No new tasks: []"""


def _parse_extractor_response(raw: str) -> list[str]:
    """Parse the extractor's response into a list of task title strings.

    Returns an empty list if the response is malformed.
    """
    # Strip <think>...</think> tags (qwen3 models)
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Extract JSON array
    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if not match:
        return []

    try:
        parsed = json.loads(match.group())
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(parsed, list):
        return []

    return [item for item in parsed if isinstance(item, str) and item.strip()]


def extract_tasks(
    user_message: str,
    conversation_id: str,
    db,
) -> bool:
    """Run the Task Extractor and write new tasks to DB.

    Args:
        user_message: The user's current message.
        conversation_id: Active conversation ID.
        db: SQLAlchemy session.

    Returns:
        True if new tasks were extracted, False otherwise.
    """
    from auth.conversation_tasks import ConversationTask
    from auth.conversations import ConversationMessage

    # Load existing tasks for this conversation
    existing = db.query(ConversationTask).filter_by(
        conversation_id=conversation_id
    ).all()
    existing_tasks = [{"title": t.title, "status": t.status} for t in existing]

    # Load recent messages for context
    recent = (
        db.query(ConversationMessage)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(5)
        .all()
    )
    recent_messages = [
        {"role": m.role, "content": m.content}
        for m in reversed(recent)
    ]

    prompt = _build_extractor_prompt(user_message, existing_tasks, recent_messages)

    try:
        llm = ChatOllama(
            model=TASK_EXTRACTOR_MODEL,
            temperature=0,
            base_url="http://localhost:11434",
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        new_titles = _parse_extractor_response(response.content)
    except Exception as e:
        logger.warning("Task Extractor failed (%s), assuming no new tasks", e)
        return False

    if not new_titles:
        logger.info("Task Extractor: no new tasks")
        return False

    # Write new tasks to DB
    for title in new_titles:
        db.add(ConversationTask(
            conversation_id=conversation_id,
            title=title,
        ))
    db.commit()

    logger.info("Task Extractor: %d new tasks: %s", len(new_titles), new_titles)
    return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_task_extractor.py -v`
Expected: All 10 tests PASS

- [ ] **Step 6: Commit**

```bash
git add task_extractor.py tests/test_task_extractor.py config.py
git commit -m "feat: add Task Extractor — 1.7B worker for task extraction"
```

---

## Task 4: Tool Curator

**Files:**
- Create: `tool_curator.py`
- Create: `tests/test_tool_curator.py`
- Modify: `config.py`

- [ ] **Step 1: Add config key**

In `config.py`, add:

```python
TOOL_CURATOR_MODEL = os.environ.get("TOOL_CURATOR_MODEL", "qwen3:1.7b")
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_tool_curator.py
"""Tests for Tool Curator prompt building, response parsing, and short-circuit."""
from tool_curator import (
    _build_curator_prompt,
    _parse_curator_response,
    CurationResult,
)
from workflow_groups import WORKFLOW_GROUPS


class TestBuildPrompt:
    def test_includes_tasks(self):
        prompt = _build_curator_prompt(
            tasks=[{"title": "scrape a website", "status": "pending"}],
            user_tool_names=["read", "write"],
        )
        assert "scrape a website" in prompt

    def test_includes_user_tools(self):
        prompt = _build_curator_prompt(
            tasks=[{"title": "task", "status": "pending"}],
            user_tool_names=["read", "write"],
        )
        assert "read" in prompt
        assert "write" in prompt

    def test_includes_workflow_groups(self):
        prompt = _build_curator_prompt(
            tasks=[{"title": "task", "status": "pending"}],
            user_tool_names=[],
        )
        for name in WORKFLOW_GROUPS:
            assert name in prompt


class TestParseResponse:
    def test_pass_action(self):
        result = _parse_curator_response('{"action": "pass"}')
        assert result == CurationResult(action="pass", groups=[], reason="")

    def test_recommend_action(self):
        result = _parse_curator_response(
            '{"action": "recommend", "groups": ["Web Tools"], "reason": "Aids with scraping"}'
        )
        assert result.action == "recommend"
        assert result.groups == ["Web Tools"]
        assert result.reason == "Aids with scraping"

    def test_unknown_group_filtered(self):
        result = _parse_curator_response(
            '{"action": "recommend", "groups": ["Web Tools", "Fake Group"], "reason": "test"}'
        )
        assert result.groups == ["Web Tools"]

    def test_all_groups_invalid_becomes_pass(self):
        result = _parse_curator_response(
            '{"action": "recommend", "groups": ["Nonexistent"], "reason": "test"}'
        )
        assert result.action == "pass"

    def test_malformed_returns_pass(self):
        result = _parse_curator_response("gibberish")
        assert result.action == "pass"

    def test_with_think_tags(self):
        raw = '<think>analyzing</think>{"action": "recommend", "groups": ["Accounting"], "reason": "Needs bookkeeping"}'
        result = _parse_curator_response(raw)
        assert result.action == "recommend"
        assert result.groups == ["Accounting"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_tool_curator.py -v`
Expected: FAIL with "No module named 'tool_curator'"

- [ ] **Step 4: Write the implementation**

```python
# tool_curator.py
"""Tool Curator — 1.7B worker #2.

Reads the task list and user's active tools, then either passes through
(tools are sufficient) or recommends additional workflow groups.
Short-circuits entirely when no new tasks were extracted.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

from config import TOOL_CURATOR_MODEL
from workflow_groups import WORKFLOW_GROUPS

logger = logging.getLogger(__name__)

# Per-conversation cache: conversation_id → last tool names
_tool_cache: dict[str, list[str]] = {}


@dataclass
class CurationResult:
    action: str  # "pass" or "recommend"
    groups: list[str] = field(default_factory=list)
    reason: str = ""


def _build_curator_prompt(
    tasks: list[dict],
    user_tool_names: list[str],
) -> str:
    """Build the prompt for the Tool Curator model."""
    task_lines = "\n".join(f"- [{t['status']}] {t['title']}" for t in tasks)
    tool_list = ", ".join(user_tool_names) if user_tool_names else "(none)"
    group_lines = "\n".join(
        f"- {name}: {g.tooltip}" for name, g in WORKFLOW_GROUPS.items()
    )

    return f"""You are a tool curation agent. Given the user's tasks and their currently
active tools, decide if additional workflow groups are needed.

Tasks:
{task_lines}

User's active tools: {tool_list}

Available workflow groups:
{group_lines}

Rules:
- Never remove tools the user has chosen.
- If the user's tools are sufficient for all tasks, return: {{"action": "pass"}}
- If additional groups would help, return:
  {{"action": "recommend", "groups": ["Group Name"], "reason": "short reason"}}
- Recommend the minimum set of groups needed.
- Keep the reason under 15 words.

Return ONLY JSON."""


def _parse_curator_response(raw: str) -> CurationResult:
    """Parse the curator's response into a CurationResult.

    Returns a pass-through result if the response is malformed.
    """
    # Strip <think>...</think> tags
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Extract JSON object
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return CurationResult(action="pass")

    try:
        parsed = json.loads(match.group())
    except (json.JSONDecodeError, TypeError):
        return CurationResult(action="pass")

    if not isinstance(parsed, dict):
        return CurationResult(action="pass")

    action = parsed.get("action", "pass")
    if action != "recommend":
        return CurationResult(action="pass")

    # Validate group names against registry
    raw_groups = parsed.get("groups", [])
    valid_groups = [g for g in raw_groups if isinstance(g, str) and g in WORKFLOW_GROUPS]

    if not valid_groups:
        return CurationResult(action="pass")

    reason = parsed.get("reason", "")
    if not isinstance(reason, str):
        reason = ""

    return CurationResult(action="recommend", groups=valid_groups, reason=reason)


def curate_tools(
    conversation_id: str,
    user_tool_names: list[str],
    has_new_tasks: bool,
    db,
) -> CurationResult:
    """Run the Tool Curator for this conversation.

    Short-circuits (returns pass) if no new tasks were extracted.

    Args:
        conversation_id: Active conversation ID.
        user_tool_names: Tool names from user preferences.
        has_new_tasks: Whether the Task Extractor found new tasks.
        db: SQLAlchemy session.

    Returns:
        CurationResult with action, groups, and reason.
    """
    # Short-circuit: no new tasks = no inference needed
    if not has_new_tasks:
        logger.info("Tool Curator: no new tasks, passing through")
        return CurationResult(action="pass")

    from auth.conversation_tasks import ConversationTask

    # Load all non-done tasks for this conversation
    tasks = db.query(ConversationTask).filter(
        ConversationTask.conversation_id == conversation_id,
        ConversationTask.status != "done",
    ).all()
    task_dicts = [{"title": t.title, "status": t.status} for t in tasks]

    if not task_dicts:
        return CurationResult(action="pass")

    prompt = _build_curator_prompt(task_dicts, user_tool_names)

    try:
        llm = ChatOllama(
            model=TOOL_CURATOR_MODEL,
            temperature=0,
            base_url="http://localhost:11434",
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        result = _parse_curator_response(response.content)

        logger.info("Tool Curator: action=%s, groups=%s", result.action, result.groups)
        return result

    except Exception as e:
        logger.warning("Tool Curator failed (%s), passing through", e)
        return CurationResult(action="pass")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_tool_curator.py -v`
Expected: All 10 tests PASS

- [ ] **Step 6: Commit**

```bash
git add tool_curator.py tests/test_tool_curator.py config.py
git commit -m "feat: add Tool Curator — 1.7B worker for workflow group recommendations"
```

---

## Task 5: Frontend — Recommendation Stream Event

**Files:**
- Modify: `frontend/src/atoms/stream.ts`
- Modify: `frontend/src/api/chat.ts`

- [ ] **Step 1: Add recommendation to StreamEvent type**

In `frontend/src/atoms/stream.ts`, add to the `StreamEvent` union:

```typescript
| { type: 'recommendation'; groups: string[]; reason: string }
```

- [ ] **Step 2: Add parseStreamLine case**

In the `parseStreamLine` function in the same file, add a case for `recommendation`:

```typescript
if ('recommendation' in data) {
  return {
    type: 'recommendation',
    groups: data.recommendation.groups,
    reason: data.recommendation.reason,
  };
}
```

- [ ] **Step 3: Add recommendation response API call**

In `frontend/src/api/chat.ts`, add:

```typescript
export async function respondToRecommendation(
  conversationId: string,
  acceptedGroups: string[],
): Promise<void> {
  const resp = await fetch('/api/chat/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      accepted_groups: acceptedGroups,
    }),
    credentials: 'include',
  });
  if (!resp.ok) throw new Error(`Recommendation response failed: ${resp.status}`);
}
```

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend && npx vitest run`
Expected: Existing tests still pass. No new test failures from type additions.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/atoms/stream.ts frontend/src/api/chat.ts
git commit -m "feat: add recommendation stream event type and API call"
```

---

## Task 6: Frontend — Recommendation Chip UI

**Files:**
- Modify: `frontend/src/providers/ChatProvider.tsx`
- Modify: `frontend/src/components/organisms/InputBar.tsx`

- [ ] **Step 1: Add recommendation state to ChatProvider**

In `ChatProvider.tsx`, add to the context type and state:

```typescript
// Add to ChatContextType
recommendation: { groups: string[]; reason: string } | null;
acceptRecommendation: () => void;
dismissRecommendation: () => void;
```

Add state:

```typescript
const [recommendation, setRecommendation] = useState<{ groups: string[]; reason: string } | null>(null);
```

In the stream event handler, add a case for `recommendation`:

```typescript
case 'recommendation':
  setRecommendation({ groups: event.groups, reason: event.reason });
  break;
```

Add accept/dismiss handlers:

```typescript
const acceptRecommendation = useCallback(async () => {
  if (!recommendation || !conversationId) return;
  await respondToRecommendation(conversationId, recommendation.groups);
  setRecommendation(null);
}, [recommendation, conversationId]);

const dismissRecommendation = useCallback(async () => {
  if (!conversationId) return;
  await respondToRecommendation(conversationId, []);
  setRecommendation(null);
}, [conversationId]);
```

- [ ] **Step 2: Add recommendation chip to InputBar**

In `InputBar.tsx`, consume the new context values and render the chip above the input when a recommendation exists:

```tsx
const { recommendation, acceptRecommendation, dismissRecommendation } = useChat();

{recommendation && (
  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-4 py-3 rounded-xl
    bg-[var(--glass-bg-solid)] border border-[var(--accent)] backdrop-blur-xl
    flex items-center gap-3 shadow-lg z-20">
    <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent)]" />
    <span className="text-[var(--text-primary)] text-sm">
      <strong>+ {recommendation.groups.join(', ')}</strong>
      <span className="text-[var(--text-muted)] ml-2">— {recommendation.reason}</span>
    </span>
    <button
      onClick={acceptRecommendation}
      className="px-3 py-1 rounded-lg bg-[var(--accent)] text-[var(--bg-base)] font-semibold
        text-sm hover:opacity-90 transition-opacity"
    >
      Accept
    </button>
    <button
      onClick={dismissRecommendation}
      className="px-3 py-1 rounded-lg border border-[var(--text-muted)] text-[var(--text-muted)]
        text-sm hover:opacity-80 transition-opacity"
    >
      Dismiss
    </button>
  </div>
)}
```

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && npx vitest run`
Expected: All existing tests pass.

- [ ] **Step 4: Visual verification**

Run: `cd frontend && npm run dev`
Verify: InputBar renders normally without a recommendation. Recommendation chip styling matches existing overlay patterns (same position, glassmorphism, accent colors).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/providers/ChatProvider.tsx frontend/src/components/organisms/InputBar.tsx
git commit -m "feat: add recommendation chip UI with accept/dismiss"
```

---

## Task 7: Backend Integration — Wire Pipeline into main.py

**Files:**
- Modify: `main.py`
- Delete: `prepass.py`

- [ ] **Step 1: Add the recommendation endpoint**

In `main.py`, add a new endpoint for handling recommendation responses. This uses a per-conversation threading Event to signal the streaming generator:

```python
import threading

# Per-conversation recommendation responses
_recommendation_events: dict[str, threading.Event] = {}
_recommendation_responses: dict[str, list[str]] = {}


@app.route("/api/chat/recommend", methods=["POST"])
@login_required
def handle_recommendation():
    """Handle user's accept/dismiss of a tool recommendation."""
    data = request.get_json(force=True)
    conversation_id = data.get("conversation_id")
    accepted_groups = data.get("accepted_groups", [])

    if not conversation_id:
        return jsonify({"error": "conversation_id required"}), 400

    _recommendation_responses[conversation_id] = accepted_groups
    event = _recommendation_events.get(conversation_id)
    if event:
        event.set()

    return jsonify({"status": "ok"})
```

- [ ] **Step 2: Add the workflow groups API endpoint**

```python
from workflow_groups import WORKFLOW_GROUPS, tools_for_groups


@app.route("/api/workflows", methods=["GET"])
@login_required
def list_workflows():
    """List available workflow groups."""
    groups = []
    for name, group in WORKFLOW_GROUPS.items():
        groups.append({
            "name": name,
            "tooltip": group.tooltip,
            "tool_count": len(group.tools),
            "tools": group.tools,
        })
    return jsonify({"groups": groups})
```

- [ ] **Step 3: Replace prepass calls in chat_stream**

In the `chat_stream` function, replace lines 347-349 (the prepass block):

```python
# OLD — delete these lines:
# print(f"[PREPASS_START]", flush=True)
# fallback_names = _get_user_selected_tools()
# tool_names = select_tools(user_msg, fallback_names)

# NEW — Task Extractor + Tool Curator pipeline:
from task_extractor import extract_tasks
from tool_curator import curate_tools

user_tool_names = _get_user_selected_tools()
has_new_tasks = extract_tasks(user_msg, conversation_id, db)
curation = curate_tools(conversation_id, user_tool_names, has_new_tasks, db)
```

- [ ] **Step 4: Add recommendation pause/resume logic in the generator**

Inside the `generate()` function, before building the system prompt, add the recommendation flow:

```python
# Inside generate(), before building tool schemas:
accepted_groups = []

if curation.action == "recommend":
    # Send recommendation to frontend
    yield json.dumps({"recommendation": {
        "groups": curation.groups,
        "reason": curation.reason,
    }}) + "\n"

    # Wait for user response (accept/dismiss)
    event = threading.Event()
    _recommendation_events[conversation_id] = event
    event.wait(timeout=120)  # 2 min timeout; on timeout, acts as dismiss (empty groups)

    accepted_groups = _recommendation_responses.pop(conversation_id, [])
    _recommendation_events.pop(conversation_id, None)

    print(f"[CURATION] User accepted groups: {accepted_groups}", flush=True)

# Note: threading.Event blocks a server thread. Acceptable for low-concurrency
# local Ollama deployment. If scaling to many concurrent users, replace with
# async (e.g., asyncio.Event with an ASGI server).

# Resolve final tool set
extra_tools = tools_for_groups(accepted_groups)
tool_names = list(set(user_tool_names + extra_tools))

print(f"[CHAT] final tool set: {len(tool_names)} tools: {tool_names}", flush=True)
```

- [ ] **Step 5: Remove old prepass import**

In `main.py`, remove:

```python
from prepass import load_tool_index, select_tools
```

And remove the startup block:

```python
# Delete this block:
# with app.app_context():
#     try:
#         load_tool_index()
#     except Exception as e:
#         logging.getLogger(__name__).warning("Failed to load tool index at startup: %s", e)
```

- [ ] **Step 6: Delete prepass.py**

```bash
rm prepass.py
```

- [ ] **Step 7: Run backend tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass. Any tests that imported from `prepass` need to be removed or updated (check `tests/` for prepass imports).

- [ ] **Step 8: Run frontend tests**

Run: `cd frontend && npx vitest run`
Expected: All tests pass.

- [ ] **Step 9: Manual integration test**

1. Start the backend: `uv run python main.py --serve`
2. Start the frontend: `cd frontend && npm run dev`
3. Open the app, select a model, start a conversation
4. Send: "Go to https://example.com and scrape the page"
5. Verify: recommendation chip appears suggesting "Web Tools"
6. Click Accept → agent runs with web tools bound
7. Send: "try again" → no chip (no new tasks), agent runs with same tools
8. Send: "now create a journal entry for the $50 purchase" → chip suggests "Accounting"

- [ ] **Step 10: Commit**

```bash
git add main.py
git rm prepass.py
git add -A  # catch any remaining changes
git commit -m "feat: wire task-aware tool curation pipeline, remove prepass"
```

---

## Task 8: Cleanup and Config

**Files:**
- Modify: `config.py`
- Modify: `tests/` (remove prepass test if it exists)

- [ ] **Step 1: Remove PREPASS_MODEL from config**

In `config.py`, remove:

```python
PREPASS_MODEL = _os.environ.get("PREPASS_MODEL", "qwen3:1.7b")
```

The replacement keys `TASK_EXTRACTOR_MODEL` and `TOOL_CURATOR_MODEL` were already added in Tasks 3 and 4.

- [ ] **Step 2: Check for stale prepass references**

Run: `grep -r "prepass\|PREPASS\|select_tools\|load_tool_index" --include="*.py" .`

Remove or update any remaining references. Expected locations:
- `tests/test_integration_accounting.py` may mock `select_tools` — update to mock `extract_tasks` + `curate_tools` instead, or remove the mock if no longer needed.
- Delete any `tests/test_prepass*.py` files that test the old prepass module.

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v && cd frontend && npx vitest run`
Expected: All tests pass with zero prepass references remaining.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove prepass references, finalize config"
```
