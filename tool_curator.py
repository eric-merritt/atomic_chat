"""Tool Curator — 1.7B worker #2.

Reads the task list and user's active tools, then either passes through
(tools are sufficient) or recommends additional workflow groups.
Short-circuits entirely when no new tasks were extracted.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

from config import TOOL_CURATOR_MODEL
from workflow_groups import WORKFLOW_GROUPS

logger = logging.getLogger(__name__)

_LOG_DIR = os.path.join(os.path.dirname(__file__), "training_data", "logs")
_CURATOR_LOG = os.path.join(_LOG_DIR, "tool_curator.jsonl")

_SYSTEM_MSG = (
    "You are a tool curation agent. Given tasks and the user's active tools, "
    "decide if additional workflow groups are needed. Never remove user-chosen "
    "tools. Recommend the minimum groups needed. Return ONLY JSON: "
    '{\"action\":\"pass\"} or {\"action\":\"recommend\",\"groups\":[...],\"reason\":\"...\"}'
)


def _log_exchange(prompt: str, response: str):
    """Append a training-format JSONL line for this exchange."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        entry = {
            "messages": [
                {"role": "system", "content": _SYSTEM_MSG},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ]
        }
        with open(_CURATOR_LOG, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Failed to log curator exchange: %s", e)

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
    user_set = set(user_tool_names)

    # Categorize groups
    active_groups = []
    partial_groups = []
    missing_groups = []
    for name, g in WORKFLOW_GROUPS.items():
        group_tools = set(g.tools)
        if group_tools.issubset(user_set):
            active_groups.append(f'- "{name}" — {g.tooltip}')
        elif group_tools & user_set:
            partial_groups.append(f'- "{name}" — {g.tooltip} (partially active)')
        else:
            missing_groups.append(f'- "{name}" — {g.tooltip}')

    active_str = "\n".join(active_groups) if active_groups else "(none)"
    available_str = "\n".join(missing_groups + partial_groups) if (missing_groups or partial_groups) else "(none — user has all groups)"

    return f"""You are a tool curation agent. You recommend WORKFLOW GROUPS, never individual tools.

Tasks:
{task_lines}

User's active groups:
{active_str}

Available workflow groups (NOT yet active):
{available_str}

IMPORTANT: You must recommend GROUPS by their exact name (e.g. "Web Tools", "Accounting"), NOT individual tool names.

Rules:
- Never remove tools the user has chosen.
- If the active groups are sufficient for the tasks, return: {{"action": "pass"}}
- If a task requires a missing group, return:
  {{"action": "recommend", "groups": ["Exact Group Name"], "reason": "short reason"}}
- The "groups" array MUST contain group names from the list above, NOT tool names.
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
        from config import OLLAMA_CURATION_NUM_CTX
        llm = ChatOllama(
            model=TOOL_CURATOR_MODEL,
            temperature=0,
            base_url="http://localhost:11434",
            num_ctx=OLLAMA_CURATION_NUM_CTX,
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content
        result = _parse_curator_response(raw)
        _log_exchange(prompt, raw)

        logger.info("Tool Curator: action=%s, groups=%s", result.action, result.groups)
        return result

    except Exception as e:
        logger.warning("Tool Curator failed (%s), passing through", e)
        return CurationResult(action="pass")
