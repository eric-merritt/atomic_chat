"""Change Hats — 7B workflow analysis agent (two-call split).

Call 1 (GATE): Classify message as conversational / tool_required / mixed.
Call 2 (PLAN): If tools needed, build hierarchical task chain with subtasks.

Task Structure:
  GLOBAL TaskSpace: Chain = TaskList, ChainLink = Task
  LOCAL  TaskSpace: Chain = Task,     ChainLink = SubTask
"""

import json
import logging
import os
import re

import ollama as ollama_client
from qwen_agent.llm import get_chat_model

from config import TOOL_CURATOR_MODEL
from pipeline.workflow_groups import WORKFLOW_GROUPS, TOOL_REF, group_for_tool

logger = logging.getLogger(__name__)

_LOG_DIR = os.path.join(os.path.dirname(__file__), "training_data", "logs")
_HATS_LOG = os.path.join(_LOG_DIR, "change_hats.jsonl")



# ── Call 1: Gate ─────────────────────────────────────────────

_GATE_SYSTEM = """You classify user messages into exactly one category. Respond with ONLY the category name, nothing else.

CONVERSATIONAL — Choose when the user's request requires no external data or systems. Greetings, general coding questions, and asking for advice on a topic all fall into this category. If the user needs up to date information on a topic, tool calls may be necessary to search web sources.
TOOL_REQUIRED — Choose when the agent must interact with external systems to fulfill the user's request.
MIXED — has both. A question AND an action request in the same message. e.g. What's a good bash command I can run to search for files with the string "alibaster" in their text content? Are there any new GUI tools that will do this for me?

Examples:
"What does this error mean?" → CONVERSATIONAL
"Hey how's it going" → CONVERSATIONAL
"Search eBay for RTX 3090 under $800" → TOOL_REQUIRED
"Read the file at ~/config.py and fix the bug on line 12" → TOOL_REQUIRED
"What's the best approach? Also search eBay for RTX 3090" → MIXED
"Do the tasks" → Requires inference to define. Read the user defined task title.
"Explain what a LoRA is" → CONVERSATIONAL"""


def _gate_classify(user_message: str, recent_messages: list[dict]) -> str:
    """Call 1: fast classification. Returns 'conversational', 'tool_required', or 'mixed'."""
    if recent_messages:
        history = "\n".join(
            f"{m['role']}: {m['content'][:150]}" for m in recent_messages[-3:]
        )
        user_prompt = f"Recent context:\n{history}\n\nClassify this message: \"{user_message}\""
    else:
        user_prompt = f"Classify this message: \"{user_message}\""

    try:
        response = ollama_client.chat(
            model=TOOL_CURATOR_MODEL,
            messages=[
                {"role": "system", "content": _GATE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            options={"num_ctx": 16000, "temperature": 0},
        )
        raw = response.message.content.strip().lower()
        # Strip think tags
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip().lower()

        if "tool_required" in raw or "tool required" in raw:
            return "tool_required"
        if "mixed" in raw:
            return "mixed"
        return "conversational"
    except Exception as e:
        logger.warning("Gate classification failed (%s), defaulting to conversational", e)
        return "conversational"


# ── Call 2: Plan ─────────────────────────────────────────────

_PLAN_SYSTEM = """You are a logical workflow planner. Build a task chain from the user's message.

## Structure
GLOBAL: TaskList = ordered Chain of Tasks
LOCAL:  Task = ordered Chain of SubTasks (concrete tool operations)

## Rules
- Preserve ALL details: URLs, prices, names, filters, file paths, quantities
- Order by dependency — what must happen first
- If a subtask needs output from a prior step, say so in "detail"
- "action" must be a tool name from AVAILABLE TOOLS, or "respond" for text answers
- Do NOT invent tool names — only use tools from the list provided"""

_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "task_list": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "subtasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step": {"type": "integer"},
                                "action": {"type": "string"},
                                "detail": {"type": "string"},
                            },
                            "required": ["step", "action", "detail"],
                        },
                    },
                },
                "required": ["title", "subtasks"],
            },
        },
    },
    "required": ["task_list"],
}


def _plan_tasks(
    user_message: str,
    existing_tasks: list[dict],
    recent_messages: list[dict],
    available_tools: list[str],
) -> list[dict]:
    """Call 2: build task chain with subtasks. Returns task_list."""
    if existing_tasks:
        task_lines = "\n".join(
            f"- [{t['status']}] {t['title']}" for t in existing_tasks
        )
    else:
        task_lines = "(none)"

    if recent_messages:
        history = "\n".join(
            f"{m['role']}: {m['content'][:200]}" for m in recent_messages[-5:]
        )
    else:
        history = "(start of conversation)"

    # Build compact tool reference grouped by category
    tool_set = set(available_tools)
    group_refs = []
    for gname, g in WORKFLOW_GROUPS.items():
        entries = [f"{t}: {TOOL_REF.get(t, '?')}" for t in g.tools if t in tool_set]
        if entries:
            group_refs.append(f"{gname}: {', '.join(entries)}")
    tool_ref_text = "\n".join(group_refs) if group_refs else "(none)"

    user_prompt = f"""EXISTING TASKS (do NOT re-extract these):
{task_lines}

RECENT CONVERSATION:
{history}

TOOLS (name: description):
{tool_ref_text}

USER MESSAGE: "{user_message}"

Build the task chain. Return JSON only."""

    try:
        response = ollama_client.chat(
            model=TOOL_CURATOR_MODEL,
            messages=[
                {"role": "system", "content": _PLAN_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            format=_PLAN_SCHEMA,
            options={"num_ctx": 16000, "temperature": 0},
        )
        raw = response.message.content.strip()
        # Strip think tags
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        parsed = json.loads(raw)
        task_list = parsed.get("task_list", [])

        # Validate tool names
        tool_set = set(available_tools) | {"respond", "mark_task_done"}
        for task in task_list:
            for subtask in task.get("subtasks", []):
                if subtask.get("action") not in tool_set:
                    subtask["action"] = "respond"

        _log_exchange(user_prompt, raw)
        return task_list

    except Exception as e:
        logger.warning("Plan call failed (%s), returning empty plan", e)
        return []


# ── Public API ───────────────────────────────────────────────

def _log_exchange(prompt: str, response: str):
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        entry = {
            "prompt": prompt,
            "response": response,
        }
        with open(_HATS_LOG, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Failed to log change_hats exchange: %s", e)


def analyze_message(
    user_message: str,
    conversation_id: str,
    available_tools: list[str],
    db,
) -> dict:
    """Run the two-call workflow analysis.

    Returns:
        {
            "classification": "conversational" | "tool_required" | "mixed",
            "task_list": [{"title": str, "subtasks": [{"step": int, "action": str, "detail": str}]}]
        }
    """
    from auth.conversation_tasks import ConversationTask
    from auth.conversations import ConversationMessage

    # Load context
    existing = db.query(ConversationTask).filter_by(
        conversation_id=conversation_id
    ).all()
    existing_tasks = [{"title": t.title, "status": t.status} for t in existing]

    recent = (
        db.query(ConversationMessage)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(10)
        .all()
    )
    recent_messages = [
        {"role": m.role, "content": m.content}
        for m in reversed(recent)
    ]

    # Call 1: Gate
    classification = _gate_classify(user_message, recent_messages)
    logger.info("change_hats GATE: %s", classification)

    # Call 2: Plan (only if tools needed)
    task_list = []
    if classification in ("tool_required", "mixed"):
        task_list = _plan_tasks(
            user_message, existing_tasks, recent_messages, available_tools
        )
        logger.info(
            "change_hats PLAN: %d tasks — %s",
            len(task_list),
            [t.get("title", "")[:40] for t in task_list],
        )

    return {
        "classification": classification,
        "task_list": task_list,
    }
