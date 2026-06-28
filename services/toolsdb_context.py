"""Tool routing via the codebase-memory-mcp SQLite graph (tools.db).

An alternative to the graphify->Neo4j router (services/neo4j_context.py). Reads
the MCP's richer graph directly: FTS5 keyword search over tool nodes + the
graph's edge types, with prose summaries injected from graphify's graph.json
(the MCP graph stores structure/metrics but no prose summary).

Returns the SAME (prompt_block, tool_names) contract as
routes.chat._build_neo4j_tool_context, so chat.py can swap routers behind a flag.

Read-only: tools.db is opened read-only (it is WAL, so this is safe alongside
the running MCP server). Nothing here writes to the MCP graph.
"""

import os
import re
import json
import sqlite3
import logging
from functools import lru_cache

from qwen_agent.tools.base import TOOL_REGISTRY as QW_TOOL_REGISTRY

log = logging.getLogger(__name__)

# The MCP keys its tools-only graph under this project name / db file.
_PROJECT = "home-ermer-devproj-python-atomic_chat-tools"
_DB_PATH = os.path.expanduser(f"~/.cache/codebase-memory-mcp/{_PROJECT}.db")
# graphify graph that carries the prose summaries (one level up from services/).
_GRAPH_JSON = os.path.join(os.path.dirname(os.path.dirname(__file__)), "graph.json")

# Matches register_tool('name'), register_tool("name"), and the escaped form
# register_tool(\"name\") that appears when the source used double quotes (the
# decorator is stored as a JSON string, so its quotes get backslash-escaped).
_DECORATOR_NAME_RE = re.compile(r"register_tool\(\s*\\?['\"]([^'\"\\]+)\\?['\"]")
_FTS_TERM_RE = re.compile(r"[A-Za-z0-9_]{3,}")


@lru_cache(maxsize=1)
def _summary_map() -> dict:
    """class_name -> prose summary, loaded once from graphify's graph.json."""
    try:
        with open(_GRAPH_JSON) as graph_file:
            graph = json.load(graph_file)
    except (OSError, ValueError) as load_err:
        log.warning("toolsdb: could not load graph.json summaries: %s", load_err)
        return {}
    return {
        node["name"]: node["summary"]
        for node in graph.get("nodes", [])
        if node.get("type") == "Class" and node.get("summary")
    }


def _connect():
    """Open tools.db read-only. Returns None if the MCP graph is absent."""
    if not os.path.exists(_DB_PATH):
        return None
    return sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)


def _registered_name(decorators_json: str) -> str:
    """Extract the @register_tool('name') registered name from a node's
    decorators property. Returns '' when the class is not a registered tool."""
    if not decorators_json:
        return ""
    match = _DECORATOR_NAME_RE.search(decorators_json)
    return match.group(1) if match else ""


def _fts_query(task_description: str) -> str:
    """Build a safe FTS5 OR-query from the task: 3+ char alnum terms only."""
    terms = _FTS_TERM_RE.findall(task_description.lower())
    return " OR ".join(dict.fromkeys(terms)) if terms else ""


def score_tools_fts(task_description: str, limit: int = 10) -> list[dict]:
    """Return registered tool nodes ranked by relevance to the task.

    Hybrid scoring: each tool's searchable text = class name + registered name +
    graphify summary (the summary is the richest signal — the FTS index alone
    only covers name/file_path, which is too thin to match e.g. "sort photos by
    quality" against VisionGradingTool). Tools are ranked by how many task terms
    hit that combined text, with name/registered-name matches weighted heavier.

    Each result: {name, registered, summary, file_path}. Only classes whose
    @register_tool name maps to a live registry entry are returned.
    """
    terms = set(_FTS_TERM_RE.findall(task_description.lower()))
    if not terms:
        return []
    conn = _connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT n.name, n.file_path,
                   json_extract(n.properties, '$.decorators') AS decorators,
                   json_extract(n.properties, '$.docstring') AS docstring
            FROM nodes n
            WHERE n.label = 'Class'
            """
        ).fetchall()
    except sqlite3.Error as query_err:
        log.warning("toolsdb: tool query failed: %s", query_err)
        return []
    finally:
        conn.close()

    summaries = _summary_map()
    scored = []
    for class_name, file_path, decorators, docstring in rows:
        registered = _registered_name(decorators)
        if not registered or registered not in QW_TOOL_REGISTRY:
            continue
        # Prefer graphify's curated summary; fall back to the tool's docstring
        # from tools.db (fresher — covers tools added after graph.json was built,
        # e.g. viz_quality_sort).
        summary = summaries.get(class_name) or (docstring or "").strip()
        name_text = f"{class_name} {registered}".lower()
        summary_text = summary.lower()
        # name/registered hits weigh 3x; summary hits 1x.
        score = sum(3 for term in terms if term in name_text) + sum(
            1 for term in terms if term in summary_text
        )
        if score:
            scored.append(
                {
                    "name": class_name,
                    "registered": registered,
                    "summary": summary[:150],
                    "file_path": file_path,
                    "_score": score,
                }
            )
    scored.sort(key=lambda tool: tool["_score"], reverse=True)
    return scored[:limit]


def build_toolsdb_context(task_description: str) -> tuple[str, list[str]]:
    """Drop-in replacement for _build_neo4j_tool_context.

    Returns (prompt_block, tool_names): a RELEVANT TOOLS block for the system
    prompt and the matching registered tool names for the agent's function_list.
    """
    tools = score_tools_fts(task_description, limit=10)
    if not tools:
        return "", []

    lines = [
        f"- {tool['registered']}: {tool['summary']}" if tool["summary"]
        else f"- {tool['registered']}"
        for tool in tools
    ]
    prompt_block = "\n\n## RELEVANT TOOLS FOR THIS TASK\n" + "\n".join(lines)
    names = list(dict.fromkeys(tool["registered"] for tool in tools))
    return prompt_block, names
