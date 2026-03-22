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
