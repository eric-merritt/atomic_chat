"""Tool pre-pass: lightweight LLM selects relevant tools per-turn.

Flow:
  1. At startup, connect to MCP server at tools.eric-merritt.com via MCP client
  2. Call tools/list to get available tools with schemas
  3. Build compact index (name -> first-line description)
  4. Each turn, ask PREPASS_MODEL which tools are needed
  5. Return list of tool names; caller fetches full schemas and binds them
"""

import asyncio
import json
import logging
import re

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from config import PREPASS_MODEL

logger = logging.getLogger(__name__)

TOOLS_SERVER_URL = "https://tools.eric-merritt.com/"

# Module-level cache
_compact_index: dict[str, str] | None = None
_known_tool_names: set[str] | None = None


def _build_compact_index(tools) -> dict[str, str]:
    """Build compact index from tool objects or dicts.

    Accepts both MCP Tool objects (with .name/.description attributes)
    and plain dicts (with "name"/"description" keys).
    """
    index = {}
    for t in tools:
        if isinstance(t, dict):
            name = t.get("name", "")
            desc = t.get("description", "")
        else:
            name = t.name
            desc = t.description or ""
        first_line = desc.split("\n")[0].strip() if desc else ""
        index[name] = first_line
    return index


async def _fetch_tool_index_async() -> dict[str, str]:
    """Connect to MCP server and fetch tool list."""
    async with streamable_http_client(TOOLS_SERVER_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return _build_compact_index(result.tools)


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
    """Fetch tool list from MCP server and cache compact index.

    Call once at startup. Returns the compact index {name: first_line_description}.
    Raises on connection failure — caller should handle gracefully.
    """
    global _compact_index, _known_tool_names

    _compact_index = asyncio.run(_fetch_tool_index_async())
    _known_tool_names = set(_compact_index.keys())

    logger.info("Tool index loaded via MCP: %d tools", len(_compact_index))
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
