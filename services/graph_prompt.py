"""Dynamic prompt builder — generates task-aware system prompts using graph.json context."""

from services.graph_query import score_tools_for_task, get_tool_details


def build_tool_context_prompt(task_description: str, max_tools: int = 10) -> str:
    """Build a prompt section listing tools relevant to the task, with summaries.

    Returns a formatted string suitable for injection into the system prompt.
    """
    tools = score_tools_for_task(task_description, limit=max_tools)
    if not tools:
        return "No tools matched this task. Use list_tools to browse available capabilities."

    # Group by category
    by_category: dict[str, list[dict]] = {}
    for t in tools:
        by_category.setdefault(t["category"], []).append(t)

    lines = ["Available tools for this task:\n"]
    for category, cat_tools in sorted(by_category.items()):
        lines.append(f"[{category}]")
        for t in cat_tools:
            desc = t["call_summary"] or t["summary"] or "(no description)"
            lines.append(f"  - {t['name']}: {desc} (relevance: {t['score']})")
        lines.append("")

    return "\n".join(lines)


def build_dynamic_system_prompt(
    task_description: str,
    base_system_prompt: str,
    max_tools: int = 10,
    include_tool_list: bool = True,
) -> str:
    """Build a complete system prompt with task-relevant tool context.

    Args:
        task_description: What the agent needs to accomplish
        base_system_prompt: The existing base system prompt (_SYSTEM_BASE from chat.py)
        max_tools: Max number of tools to surface
        include_tool_list: Whether to include the formatted tool list

    Returns:
        Complete system prompt string
    """
    tool_context = build_tool_context_prompt(task_description, max_tools)

    if include_tool_list:
        return (
            f"{base_system_prompt}\n\n"
            f"--- TASK CONTEXT ---\n"
            f"Current task: {task_description}\n\n"
            f"{tool_context}\n"
            f"Use get_params(tool_name) to get parameter schemas for any tool above.\n"
            f"--- END TASK CONTEXT ---\n"
        )

    return base_system_prompt


def build_tool_selection_hint(task_description: str, max_tools: int = 5) -> dict:
    """Return structured tool selection hint for need_tool routing.

    Returns a dict with ranked tool names and their relevance rationale.
    """
    tools = score_tools_for_task(task_description, limit=max_tools)
    return {
        "task": task_description,
        "recommended_tools": [
            {"name": t["name"], "score": t["score"], "category": t["category"]}
            for t in tools
        ],
    }
