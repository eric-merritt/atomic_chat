"""Graph visualization and tool routing API endpoints.

Neo4j is the primary backend for:
- Tool routing (score_tools_for_task via full-text index)
- Dynamic prompt building (context retrieval + injection)
- Visualization data (pattern matching + relationship traversal)

Falls back to graph.json-based services if Neo4j is unavailable.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_login import login_required

from services.neo4j_context import (
    get_viz_data as neo4j_viz_data,
    score_tools_for_task as neo4j_score_tools,
)

# [eslint nowarn]
from services.neo4j_prompt import (
    get_task_context_bundle,
)

from services.graph_query import (
    get_tool_catalog,
    get_tool_details,
    get_viz_data,
    reload_graph,
    score_tools_for_task,
)
from services.graph_prompt import (
    build_dynamic_system_prompt as legacy_prompt,
    build_tool_context_prompt as legacy_tool_context,
    build_tool_selection_hint as legacy_hint,
)

log = logging.getLogger(__name__)

graph_bp = Blueprint("graph", __name__, url_prefix="/api/graph")


@graph_bp.route("/viz", methods=["GET"])
@login_required
def graph_visualization():
    """Return visualization-optimized graph data.

    Query params:
        type: Optional node type filter (Class, Function, File, etc.)
        depth: Edge hop depth from seed nodes (default: 1)

    Uses Neo4j as primary source, falls back to graph.json.
    """
    filter_type = request.args.get("type")
    depth = int(request.args.get("depth", "1"))

    try:
        data = neo4j_viz_data(filter_type=filter_type, depth=depth)
        data["source"] = "neo4j"
        return jsonify(data)
    except Exception as e:
        log.warning("Neo4j viz query failed, falling back: %s", e)
        data = get_viz_data(filter_type=filter_type, depth=depth)
        data["source"] = "graph_json"
        return jsonify(data)


@graph_bp.route("/tools", methods=["GET"])
@login_required
def tool_catalog():
    """Return full tool catalog with categories and summaries."""
    return jsonify(get_tool_catalog())


@graph_bp.route("/tools/details", methods=["GET"])
@login_required
def tool_details():
    """Get details for specific tools.

    Query params:
        names: Comma-separated tool names
    """
    names = request.args.get("names", "").split(",")
    names = [n.strip() for n in names if n.strip()]
    if not names:
        return jsonify({"error": "names parameter required"}), 400
    return jsonify(get_tool_details(names))


@graph_bp.route("/route-tools", methods=["POST"])
@login_required
def route_tools():
    """Score tools against a task description and return ranked matches.

    Uses Neo4j full-text index for relevance scoring. Falls back to
    graph.json-based scoring if Neo4j is unavailable.
    """
    data = request.get_json(force=True)
    description = data.get("description", "")
    limit = int(data.get("limit", "15"))
    if not description:
        return jsonify({"error": "description is required"}), 400

    try:
        tools = neo4j_score_tools(description, limit=limit)
        return jsonify({"task": description, "tools": tools, "source": "neo4j"})
    except Exception as e:
        log.warning("Neo4j tool routing failed, falling back: %s", e)
        tools = score_tools_for_task(description, limit=limit)
        return jsonify({"task": description, "tools": tools, "source": "graph_json"})


@graph_bp.route("/prompt", methods=["POST"])
@login_required
def generate_prompt():
    """Generate a dynamic system prompt for a task.

    Uses Neo4j context retrieval for task-aware prompt injection.
    Falls back to graph.json-based prompt building if Neo4j is unavailable.

    Body:
        task: Task description
        base_prompt: Optional base system prompt (uses empty if omitted)
        max_tools: Max tools to include (default: 10)
    """
    data = request.get_json(force=True)
    task = data.get("task", "")
    base_prompt = data.get("base_prompt", "")
    max_tools = int(data.get("max_tools", "10"))
    if not task:
        return jsonify({"error": "task is required"}), 400

    try:
        bundle = get_task_context_bundle(task)
        return jsonify(
            {
                **bundle,
                "source": "neo4j",
            }
        )
    except Exception as e:
        log.warning("Neo4j prompt generation failed, falling back: %s", e)
        prompt = legacy_prompt(task, base_prompt, max_tools=max_tools)
        hint = legacy_hint(task)
        return jsonify(
            {
                "prompt": prompt,
                "tool_context": legacy_tool_context(task, max_tools),
                "hint": hint,
                "source": "graph_json",
            }
        )


@graph_bp.route("/reload", methods=["POST"])
@login_required
def reload():
    """Force reload graph.json from disk (after tree_walk.py regeneration)."""
    reload_graph()
    return jsonify({"status": "reloaded"})


@graph_bp.route("/neo4j/ingest", methods=["POST"])
@login_required
def neo4j_ingest():
    """Ingest graph.json into Neo4j. Clears existing data first."""
    from services.neo4j_context import clear_database, ensure_schema, ingest_graph_json

    clear_database()
    ensure_schema()
    ingest_graph_json()
    return jsonify({"status": "ingested"})


@graph_bp.route("/neo4j/status", methods=["GET"])
@login_required
def neo4j_status():
    """Check Neo4j connection status."""
    from services.neo4j_context import get_driver

    try:
        driver = get_driver()
        with driver.session() as session:
            result = session.run("RETURN 1 AS ok")
            row = result.single()
            if row and row["ok"] == 1:
                # Get node/edge counts
                counts = session.run(
                    """
                    RETURN count(DISTINCT n) AS nodes, count(DISTINCT r) AS edges
                    FROM (MATCH (n:GraphNode) WITH n
                          UNION ALL
                          MATCH ()-[r]->() WITH r)
                    """
                ).single()
                return jsonify(
                    {
                        "connected": True,
                        "uri": driver._config.host
                        if hasattr(driver, "_config")
                        else "unknown",
                        "nodes": counts["nodes"] if counts else 0,
                        "edges": counts["edges"] if counts else 0,
                    }
                )
    except Exception as e:
        return jsonify(
            {
                "connected": False,
                "error": str(e),
            }
        )
