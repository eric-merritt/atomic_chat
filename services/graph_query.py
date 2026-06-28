"""Query engine for graph.json — tool discovery, relevance scoring, and subgraph extraction."""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

GRAPH_PATH = Path(__file__).parent.parent / "graph.json"

_STOP_WORDS = frozenset({
    # Articles
    'a', 'an', 'the',
    # Prepositions
    'about', 'above', 'across', 'after', 'against', 'along', 'among',
    'around', 'at', 'before', 'behind', 'below', 'beneath', 'beside',
    'between', 'beyond', 'by', 'down', 'during', 'for', 'from', 'in',
    'inside', 'into', 'like', 'near', 'of', 'off', 'on', 'onto',
    'out', 'outside', 'over', 'past', 'since', 'through', 'to',
    'toward', 'under', 'underneath', 'until', 'unto', 'up', 'upon',
    'via', 'with', 'within', 'without',
    # Conjunctions
    'and', 'but', 'or', 'nor', 'yet', 'so',
    # Pronouns
    'i', 'me', 'my', 'mine', 'we', 'us', 'our', 'ours', 'you', 'your',
    'yours', 'he', 'him', 'his', 'she', 'her', 'hers', 'it', 'its',
    'they', 'them', 'their', 'theirs', 'who', 'whom', 'whose',
    # Demonstratives
    'this', 'that', 'these', 'those',
    # Quantifiers
    'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other',
    'some', 'such',
    # Verbs (common but low signal)
    'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did',
    'can', 'could', 'will', 'would', 'shall', 'should', 'may', 'might',
    'must', 'ought', 'need', 'want', 'use', 'using', 'get', 'got',
    # Question words
    'how', 'what', 'when', 'where', 'which', 'why',
    # Misc low-signal
    'just', 'also', 'only', 'very', 'even', 'still', 'already',
    'really', 'quite', 'much', 'many', 'lot', 'too',
    'no', 'not', 'never', 'nothing', 'nowhere',
    'here', 'there', 'then', 'once',
})

# ── Cache ──────────────────────────────────────────────────────────────────
_graph_cache: Optional[dict] = None
_tool_index: list[dict] = []


def _load_graph() -> dict:
    global _graph_cache, _tool_index
    if _graph_cache is None:
        with open(GRAPH_PATH) as f:
            _graph_cache = json.load(f)
        _tool_index = _build_tool_index(_graph_cache)
    return _graph_cache


def reload_graph():
    """Force reload graph.json (e.g. after tree_walk.py regeneration)."""
    global _graph_cache, _tool_index
    _graph_cache = None
    _tool_index = []
    _load_graph()


def _build_tool_index(graph: dict) -> list[dict]:
    """Extract all tool-class nodes with their summaries, call methods, and edges."""
    nodes = graph["nodes"]
    edges = graph["edges"]

    node_map: dict[str, dict] = {n["id"]: n for n in nodes}

    # Tool classes are identified via IMPLEMENTS_REQUIRED_METHOD edges
    # from the shared function::qwen_agent::call node.
    tool_class_ids: set[str] = set()
    for e in edges:
        if (e["source"] == "function::qwen_agent::call"
                and e.get("type") == "IMPLEMENTS_REQUIRED_METHOD"):
            tool_class_ids.add(e["target"])

    # Shared call summary (all tools use the same qwen_agent::call)
    call_node = node_map.get("function::qwen_agent::call", {})
    call_summary = call_node.get("summary")

    # TS interface-like names to skip
    ts_skip = {"ToolsResponse", "ToolParam", "WorkflowTool", "ToolContextValue",
               "ToolAdapter", "ToolCallInfo", "ToolCallPair", "Tool", "ToolCategory",
               "ToolResponse", "ToolChipProps", "ToolButtonProps"}

    tool_nodes = []
    for cid in sorted(tool_class_ids):
        n = node_map.get(cid)
        if n is None:
            continue
        if n.get("type") != "Class":
            continue
        name = n.get("name", "")
        if name in ts_skip:
            continue

        tool_nodes.append({
            "id": cid,
            "name": name,
            "summary": n.get("summary", ""),
            "call_summary": call_summary,
            "file": n.get("file", ""),
            "category": _infer_category(name, n.get("file", "")),
        })

    return tool_nodes


def _infer_category(name: str, file_path: str) -> str:
    """Infer tool category from name and file path."""
    if "web" in file_path.lower() or any(kw in name.lower() for kw in ("browser", "cookie", "url", "fetch", "download", "web_search")):
        return "web"
    if "bug_bounty" in file_path.lower() or any(kw in name.lower() for kw in ("hackerone", "bugcrowd", "intigriti", "yeswehack", "synack", "bounty")):
        return "bug_bounty"
    if "exploit" in file_path.lower() or any(kw in name.lower() for kw in ("sql_injection", "xss", "ssrf", "command_injection", "path_traversal", "rce")):
        return "exploit"
    if "of_" in file_path.lower() or any(kw in name.lower() for kw in ("scroll", "onlyfans", "save_media", "extract_image")):
        return "onlyfans"
    if "torrent" in file_path.lower() or "bt_" in file_path.lower():
        return "torrent"
    if "ecommerce" in file_path.lower() or "ec_" in file_path.lower():
        return "ecommerce"
    if "accounting" in file_path.lower() or "fa_" in file_path.lower() or any(kw in name.lower() for kw in ("ledger", "journal", "account", "inventory", "financial")):
        return "accounting"
    if "cli" in file_path.lower() or any(kw in name.lower() for kw in ("bash", "filesystem", "read", "write", "grep", "replace")):
        return "filesystem"
    if "native" in file_path.lower() or any(kw in name.lower() for kw in ("list_tools", "get_params", "need_tool", "task")):
        return "core"
    if "job" in name.lower() and "indeed" in file_path.lower():
        return "jobs"
    if "khan" in name.lower() or "khan" in file_path.lower():
        return "khan"
    if "mcp" in name.lower():
        return "mcp"
    if any(kw in name.lower() for kw in ("recorder", "start_recorder", "stop_recorder", "save_recorder")):
        return "recorder"
    if any(kw in name.lower() for kw in ("image", "vision", "describe_image")):
        return "vision"
    return "other"


def _tokenize(text: str) -> list[str]:
    """Extract meaningful words from text."""
    return [w for w in re.findall(r'[a-z]{2,}', text.lower()) if w not in _STOP_WORDS]


def score_tools_for_task(task_description: str, limit: int = 15) -> list[dict]:
    """Score all tools against a task description and return ranked list."""
    tools = _tool_index or _load_graph().get("tools", _build_tool_index(_load_graph()))
    if not tools:
        tools = _build_tool_index(_load_graph())

    task_tokens = set(_tokenize(task_description))
    if not task_tokens:
        return tools[:limit]

    scored = []
    for t in tools:
        # Combine all textual signals
        text = f"{t['name']} {t['category']} {t['summary']} {t['call_summary'] or ''}"
        tool_tokens = Counter(_tokenize(text))

        # Keyword overlap score
        keyword_score = sum(1 for tok in task_tokens if tok in tool_tokens)

        # Bonus: exact category match
        if t['category'] in task_tokens:
            keyword_score += 2

        # Bonus: name components match
        name_parts = set(re.findall(r'[A-Z][a-z]+|[a-z]+', t['name'].replace('Tool', '')))
        name_overlap = len(name_parts & task_tokens)
        keyword_score += name_overlap * 2

        # Weight by summary quality (tools with summaries rank higher)
        has_summary = 1.0 if (t['summary'] or t['call_summary']) else 0.5

        total = keyword_score * has_summary
        if total > 0:
            scored.append({
                "name": t["name"],
                "category": t["category"],
                "summary": t["summary"],
                "call_summary": t["call_summary"],
                "score": round(total, 2),
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def get_tool_details(tool_names: list[str]) -> list[dict]:
    """Get full details for specific tools by name."""
    tools = _tool_index or _build_tool_index(_load_graph())
    result = []
    for t in tools:
        if t["name"] in tool_names:
            result.append({
                "name": t["name"],
                "category": t["category"],
                "summary": t["summary"],
                "call_summary": t["call_summary"],
                "file": t["file"],
            })
    return result


def get_tool_catalog() -> dict[str, dict]:
    """Return full tool catalog: name → {category, summary, call_summary}."""
    tools = _tool_index or _build_tool_index(_load_graph())
    return {
        t["name"]: {
            "category": t["category"],
            "summary": t["summary"],
            "call_summary": t["call_summary"],
        }
        for t in tools
    }


def get_viz_data(filter_type: Optional[str] = None, depth: int = 1) -> dict:
    """Return visualization-optimized subgraph.

    Args:
        filter_type: Optional node type filter (e.g. "Class", "Function")
        depth: How many edge hops to include from seed nodes
    """
    graph = _load_graph()
    nodes = graph["nodes"]
    edges = graph["edges"]

    if filter_type:
        # Filter to matching nodes + their neighbors
        seed_ids = {n["id"] for n in nodes if n.get("type") == filter_type}
        included = set(seed_ids)

        for _ in range(depth):
            new_neighbors = set()
            for e in edges:
                if e["source"] in included:
                    new_neighbors.add(e["target"])
                if e["target"] in included:
                    new_neighbors.add(e["source"])
            included |= new_neighbors

        node_map = {n["id"]: n for n in nodes if n["id"] in included}
        filtered_edges = [e for e in edges if e["source"] in included and e["target"] in included]
    else:
        node_map = {n["id"]: n for n in nodes}
        filtered_edges = edges

    # Strip code fields for viz, keep summary + line pointers
    viz_nodes = []
    for n in node_map.values():
        viz_node = {
            "id": n["id"],
            "type": n.get("type", ""),
            "label": n.get("name", "") or n.get("label", "") or Path(n.get("path", "")).name or n["id"].split("::")[-1],
            "file": n.get("file", ""),
            "language": n.get("language", ""),
        }
        if n.get("path"):
            viz_node["path"] = n["path"]
        if n.get("summary"):
            viz_node["summary"] = n["summary"]
        if n.get("line_start") is not None:
            viz_node["line_start"] = n["line_start"]
        if n.get("line_end") is not None:
            viz_node["line_end"] = n["line_end"]
        if n.get("type") == "DependencyList" and "dependencies" in n:
            viz_node["dependencies"] = n["dependencies"]
        viz_nodes.append(viz_node)

    viz_edges = []
    for e in filtered_edges:
        viz_edges.append({
            "id": e.get("id", f"{e['source']}->{e['target']}"),
            "source": e["source"],
            "target": e["target"],
            "type": e.get("type", ""),
        })

    return {"nodes": viz_nodes, "edges": viz_edges}
