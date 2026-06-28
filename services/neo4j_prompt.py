"""Dynamic prompt injection using Neo4j context retrieval.

Builds task-aware system prompts by:
1. Searching Neo4j for relevant tools/files/concepts
2. Injecting context as a structured preamble before the base prompt
3. Including tool definitions only when relevant to the task
"""

import json
import logging
from typing import Optional

from services.neo4j_context import get_context_for_task, score_tools_for_task

log = logging.getLogger(__name__)

# ── Context injection templates ─────────────────────────────────────────────

_TOOL_CONTEXT_TEMPLATE = """
## Relevant Tools for This Task
The following tools are most relevant to your current task. Use them when appropriate:

{tool_entries}
"""

_TOOL_ENTRY_TEMPLATE = """- **{name}** (category: {category}): {summary}"""

_FILE_CONTEXT_TEMPLATE = """
## Relevant Files
The following files may be relevant to your task:

{file_entries}
"""

_FILE_ENTRY_TEMPLATE = "- `{file}` (relevance: {relevance})"


def build_dynamic_system_prompt(
    task: str,
    base_prompt: str = "",
    max_tools: int = 10,
) -> str:
    """Build a system prompt with Neo4j-derived context injected.
    
    Structure:
    1. Context preamble (relevant tools + files from Neo4j)
    2. Base system prompt (always included)
    
    Neo4j best practices:
    - Full-text index relevance scoring determines tool inclusion
    - Only inject tools above a relevance threshold
    - Include file paths for tools that reference code
    """
    context = get_context_for_task(
        task,
        include_tools=True,
        include_related_files=True,
        max_tools=max_tools,
    )

    parts = []

    # Context preamble
    preamble_parts = []

    if context.get("tools"):
        tool_entries = "\n".join(
            _TOOL_ENTRY_TEMPLATE.format(
                name=t["name"],
                category=t.get("category", "other"),
                summary=t.get("summary", "")[:200],
            )
            for t in context["tools"][:max_tools]
        )
        preamble_parts.append(_TOOL_CONTEXT_TEMPLATE.format(tool_entries=tool_entries))

    if context.get("related_files"):
        file_entries = "\n".join(
            _FILE_ENTRY_TEMPLATE.format(**f)
            for f in context["related_files"][:15]
        )
        preamble_parts.append(_FILE_CONTEXT_TEMPLATE.format(file_entries=file_entries))

    if preamble_parts:
        parts.append("## Task Context")
        parts.append("\n".join(preamble_parts))

    # Base prompt (always included)
    if base_prompt:
        parts.append(base_prompt)

    return "\n\n".join(parts)


def build_tool_context_prompt(
    task: str,
    max_tools: int = 10,
) -> str:
    """Build a focused tool context snippet for injection into the conversation.
    
    Returns only the tool-related context, suitable for appending to existing
    system prompts or conversation context.
    """
    tools = score_tools_for_task(task, limit=max_tools)

    if not tools:
        return ""

    entries = "\n".join(
        _TOOL_ENTRY_TEMPLATE.format(
            name=t["name"],
            category=t.get("category", "other"),
            summary=t.get("summary", "")[:200],
        )
        for t in tools
    )
    return _TOOL_CONTEXT_TEMPLATE.format(tool_entries=entries)


def build_tool_selection_hint(task: str, limit: int = 5) -> str:
    """Build a hint about which tools to consider for the task.
    
    Lightweight — just tool names and categories, no full summaries.
    """
    tools = score_tools_for_task(task, limit=limit)
    if not tools:
        return "No specific tools identified for this task."

    hints = ", ".join(f"{t['name']} ({t.get('category', 'other')})" for t in tools)
    return f"Consider these tools: {hints}"


def get_task_context_bundle(task: str) -> dict:
    """Return the full context bundle for a task (for API consumption).
    
    This is what the frontend /api/graph/prompt endpoint returns,
    now powered by Neo4j.
    """
    context = get_context_for_task(task)

    return {
        "task": task,
        "prompt": build_dynamic_system_prompt(task),
        "tool_context": build_tool_context_prompt(task),
        "hint": build_tool_selection_hint(task),
        "tools": context.get("tools", []),
        "related_files": context.get("related_files", []),
    }
