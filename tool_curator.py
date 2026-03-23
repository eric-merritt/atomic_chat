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
