"""Tool Curator — 1.7B worker #2.

Reads the full task list and maps each task to the specific tool(s) needed,
then determines which workflow groups must be active. Builds an exhaustive
tool plan before returning any recommendation.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field

from qwen_agent.llm import get_chat_model

from config import TOOL_CURATOR_MODEL
from workflow_groups import WORKFLOW_GROUPS, group_for_tool

logger = logging.getLogger(__name__)

_LOG_DIR = os.path.join(os.path.dirname(__file__), "training_data", "logs")
_CURATOR_LOG = os.path.join(_LOG_DIR, "tool_curator.jsonl")

_SYSTEM_MSG = (
    "You are a tool curation agent. For each task, identify the specific tool "
    "needed to complete it. Return ONLY a JSON array of task-tool mappings."
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


@dataclass
class TaskToolMapping:
    task_title: str
    tool: str           # primary tool name
    group: str | None   # workflow group the tool belongs to


@dataclass
class CurationResult:
    action: str  # "pass" or "recommend"
    groups: list[str] = field(default_factory=list)
    reason: str = ""
    task_plan: list[TaskToolMapping] = field(default_factory=list)


def _build_all_tools_reference() -> str:
    """Build a flat reference of every tool organized by group."""
    lines = []
    for group_name, g in WORKFLOW_GROUPS.items():
        tool_list = ", ".join(g.tools)
        lines.append(f'Group "{group_name}" ({g.tooltip}): {tool_list}')
    return "\n".join(lines)


def _build_curator_prompt(
    tasks: list[dict],
    user_tool_names: list[str],
) -> str:
    """Build the prompt for the Tool Curator model."""
    user_set = set(user_tool_names)

    # Build numbered task list
    task_lines = "\n".join(
        f"{i}. [{t['status']}] {t['title']}" for i, t in enumerate(tasks, 1)
    )

    # Categorize groups as active vs available
    active_groups = []
    available_groups = []
    for name, g in WORKFLOW_GROUPS.items():
        group_tools = set(g.tools)
        if group_tools.issubset(user_set) or (group_tools & user_set):
            active_groups.append(name)
        else:
            available_groups.append(name)

    tools_ref = _build_all_tools_reference()

    return f"""You are a tool curation agent. Analyze EVERY task and assign the best tool for it.

TASKS:
{task_lines}

TOOL REFERENCE (group → tools):
{tools_ref}

USER'S ACTIVE GROUPS: {', '.join(active_groups) if active_groups else '(none)'}
AVAILABLE GROUPS (not active): {', '.join(available_groups) if available_groups else '(none)'}

INSTRUCTIONS:
1. For EACH task above, pick the ONE primary tool best suited to start or complete it.
2. Use tool names from the TOOL REFERENCE, not group names.
3. If a task needs a tool from an AVAILABLE (inactive) group, still assign it — the system will recommend that group.
4. If no tool fits a task, use "mcp" to indicate the main agent should query external MCP servers.

Return ONLY a JSON array. One object per task, in order:
[
  {{"task": 1, "tool": "tool_name"}},
  {{"task": 2, "tool": "tool_name"}},
  ...
]"""


def _parse_curator_response(
    raw: str, tasks: list[dict]
) -> list[TaskToolMapping]:
    """Parse the curator's response into task-tool mappings.

    Returns an empty list if the response is malformed.
    """
    # Strip <think>...</think> tags
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

    # Build a set of all known tool names for validation
    all_tools = set()
    for g in WORKFLOW_GROUPS.values():
        all_tools.update(g.tools)
    all_tools.add("mcp")  # virtual tool for MCP delegation

    mappings = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        task_num = item.get("task", 0)
        tool_name = item.get("tool", "")

        if not isinstance(tool_name, str) or not tool_name.strip():
            continue

        tool_name = tool_name.strip()

        # Resolve task title
        idx = (int(task_num) - 1) if isinstance(task_num, (int, float)) else -1
        if 0 <= idx < len(tasks):
            title = tasks[idx]["title"]
        else:
            continue

        # Validate tool name exists
        if tool_name not in all_tools:
            # Try to find the closest match (model might use group name)
            tool_name = "mcp"  # fallback to MCP delegation

        group = group_for_tool(tool_name)
        mappings.append(TaskToolMapping(
            task_title=title,
            tool=tool_name,
            group=group,
        ))

    return mappings


def curate_tools(
    conversation_id: str,
    user_tool_names: list[str],
    has_new_tasks: bool,
    db,
) -> CurationResult:
    """Run the Tool Curator for this conversation.

    Maps each pending task to a specific tool and determines which
    workflow groups need to be activated.

    Args:
        conversation_id: Active conversation ID.
        user_tool_names: Tool names from user preferences.
        has_new_tasks: Whether the Task Extractor found new tasks.
        db: SQLAlchemy session.

    Returns:
        CurationResult with action, groups, reason, and task_plan.
    """
    from auth.conversation_tasks import ConversationTask

    # Load all non-done tasks for this conversation
    tasks = db.query(ConversationTask).filter(
        ConversationTask.conversation_id == conversation_id,
        ConversationTask.status != "done",
    ).all()
    task_dicts = [{"title": t.title, "status": t.status} for t in tasks]

    # Short-circuit: no pending tasks at all
    if not task_dicts:
        logger.info("Tool Curator: no pending tasks, passing through")
        return CurationResult(action="pass")

    prompt = _build_curator_prompt(task_dicts, user_tool_names)

    try:
        from config import qwen_curation_llm_cfg
        llm = get_chat_model(qwen_curation_llm_cfg(TOOL_CURATOR_MODEL))
        messages = [
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user", "content": prompt},
        ]
        *_, final = llm.chat(messages=messages)
        raw = final[-1].get("content", "")
        task_plan = _parse_curator_response(raw, task_dicts)
        _log_exchange(prompt, raw)

    except Exception as e:
        logger.warning("Tool Curator failed (%s), passing through", e)
        return CurationResult(action="pass")

    if not task_plan:
        logger.info("Tool Curator: could not map tasks, passing through")
        return CurationResult(action="pass")

    # Determine which groups are needed but not active
    user_set = set(user_tool_names)
    needed_groups = set()
    for m in task_plan:
        if m.group and not set(WORKFLOW_GROUPS[m.group].tools).issubset(user_set):
            needed_groups.add(m.group)

    # Filter to only groups that are truly missing (no tools active at all)
    missing_groups = []
    for g in needed_groups:
        group_tools = set(WORKFLOW_GROUPS[g].tools)
        if not (group_tools & user_set):
            missing_groups.append(g)

    if missing_groups:
        # Build reason from task plan
        reasons = []
        for g in missing_groups:
            tasks_needing = [m.task_title for m in task_plan if m.group == g]
            if tasks_needing:
                reasons.append(f"{g} for: {tasks_needing[0][:40]}")
        reason = "; ".join(reasons)[:80]

        logger.info(
            "Tool Curator: recommend %s, plan=%s",
            missing_groups,
            [(m.task_title[:30], m.tool) for m in task_plan],
        )
        return CurationResult(
            action="recommend",
            groups=missing_groups,
            reason=reason,
            task_plan=task_plan,
        )

    logger.info(
        "Tool Curator: all tools available, plan=%s",
        [(m.task_title[:30], m.tool) for m in task_plan],
    )
    return CurationResult(action="pass", task_plan=task_plan)
