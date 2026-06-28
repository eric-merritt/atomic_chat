"""Neo4j service — connection, schema, ingestion, and query utilities.

Best practices used:
- Single driver instance (connection pool managed internally)
- Parameterized queries (no string interpolation for values)
- UNWIND batch ingestion for bulk loads
- Full-text indexes for keyword search
- Session-per-query pattern with explicit database targeting
- Transaction functions (execute_write/execute_read) for retry resilience
"""

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import Neo4jError

log = logging.getLogger(__name__)

GRAPH_PATH = Path(__file__).parent.parent / "graph.json"

# ── Single driver (thread-safe, manages connection pool internally) ────────
_driver: Optional[Driver] = None

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "atomic_chat_dev")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def get_driver() -> Driver:
    """Return the singleton driver. Creates on first call."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=50,
        )
        # Verify connectivity
        _driver.verify_connectivity()
        log.info("Neo4j connected: %s", NEO4J_URI)
    return _driver


def close_driver():
    """Close the driver. Call on shutdown."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


# ── Schema setup ───────────────────────────────────────────────────────────

_SCHEMA_QUERIES = [
    # Unique constraint on node id
    "CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n:GraphNode) REQUIRE n.id IS UNIQUE",

    # Full-text index for keyword search across label, summary, name, path, type
    # Uses 'simple' analyzer (no stop-word removal, no stemming) so "chat" and "logging" match literally
    """
    CREATE FULLTEXT INDEX nodeSearch IF NOT EXISTS
    FOR (n:GraphNode) ON EACH [n.label, n.summary, n.name, n.path, n.type]
    OPTIONS { indexConfig: { `fulltext.analyzer`: 'simple' } }
    """,

    # Tool island: a dedicated full-text index over :Tool nodes only, so tool
    # routing queries never rank against File/Function/non-tool-Class nodes.
    # A :Tool is a Class that implements the required `call` method (see
    # label_tool_island). Searches name/summary/category exclusively.
    """
    CREATE FULLTEXT INDEX toolSearch IF NOT EXISTS
    FOR (n:Tool) ON EACH [n.name, n.summary, n.category]
    OPTIONS { indexConfig: { `fulltext.analyzer`: 'simple' } }
    """,
]


def label_tool_island():
    """Tag real tool classes with the :Tool label so they form a queryable
    island separate from the code graph.

    A real tool is a Class node that implements the required `call` method
    (an inbound IMPLEMENTS_REQUIRED_METHOD edge). Plain Classes with summaries
    but no such edge (FileData, DroppedImage, _BashConfirm) are NOT tools and
    stay unlabeled. Idempotent — safe to re-run.
    """
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        labeled = session.run(
            """
            MATCH (n:GraphNode {type: 'Class'})<-[:IMPLEMENTS_REQUIRED_METHOD]-(:GraphNode)
            SET n:Tool
            RETURN count(DISTINCT n) AS c
            """
        ).single()["c"]
    log.info("Tool island labeled: %d :Tool nodes", labeled)
    return labeled


def ensure_schema():
    """Create constraints and full-text indexes if they don't exist."""
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        for query in _SCHEMA_QUERIES:
            session.run(query)
    log.info("Neo4j schema ensured")


# ── Ingestion ──────────────────────────────────────────────────────────────

def ingest_graph_json():
    """Load graph.json into Neo4j using UNWIND batch upserts."""
    with open(GRAPH_PATH) as f:
        graph = json.load(f)

    driver = get_driver()
    ensure_schema()

    with driver.session(database=NEO4J_DATABASE) as session:
        # Ingest nodes in batches of 500
        nodes = graph.get("nodes", [])
        batch_size = 500
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]
            session.execute_write(_ingest_nodes, batch)

        # Ingest edges in batches of 1000
        edges = graph.get("edges", [])
        edge_batch = 1000
        for i in range(0, len(edges), edge_batch):
            batch = edges[i : i + edge_batch]
            session.execute_write(_ingest_edges, batch)

    # Tag tool classes into their own :Tool island. Must run AFTER edges exist,
    # since tool-hood is determined by the IMPLEMENTS_REQUIRED_METHOD edge.
    label_tool_island()

    log.info("Neo4j ingestion complete: %d nodes, %d edges", len(nodes), len(edges))


# Filename → category mapping (source of truth, not inference)
_FILE_CATEGORY = {
    "web.py": "web",
    "khan.py": "khan",
    "exploit.py": "exploit",
    "bug_bounty.py": "bug_bounty",
    "onlyfans.py": "onlyfans",
    "torrent.py": "torrent",
    "ecommerce.py": "ecommerce",
    "accounting.py": "accounting",
    "filesystem.py": "filesystem",
    "native.py": "core",
    "jobs.py": "jobs",
    "mcp.py": "mcp",
    "recorder.py": "recorder",
    "vision.py": "vision",
    "presentation.py": "presentation",
    "tasklist.py": "tasklist",
    "vector_store.py": "vector_store",
    "browser_session.py": "browser",
    "cli.py": "cli",
    "config.py": "config",
}


def _ingest_nodes(tx, nodes: list[dict]):
    """Upsert GraphNode nodes with all properties, serializing nested structures."""
    sanitized = []
    for n in nodes:
        flat = {}
        for k, v in n.items():
            if isinstance(v, (dict, list)):
                flat[k] = json.dumps(v)
            elif v is not None:
                flat[k] = v

        # Normalize: tree-sitter uses 'path' for File nodes, 'file' for children.
        # Merge into a single 'path' property on every node.
        if "path" not in flat and "file" in flat:
            flat["path"] = flat["file"]

        # Set searchable 'label' on File nodes (basename + dir tokens, no slashes)
        if flat.get("type") == "File" and "label" not in flat:
            p = flat.get("path", "")
            basename = p.split("/")[-1] if "/" in p else p
            dirname = p.rsplit("/", 1)[0] if "/" in p else ""
            # "routes/chat.py" → label: "routes chat.py" → both tokens indexed
            flat["label"] = f"{dirname.replace('/', ' ')} {basename}".strip()

        # Assign category from path for Class nodes (tools)
        if flat.get("type") == "Class" and "category" not in flat:
            file_path = flat.get("path", "")
            filename = file_path.split("/")[-1] if "/" in file_path else file_path
            flat["category"] = _FILE_CATEGORY.get(filename)

        flat.setdefault("type", "unknown")
        sanitized.append(flat)
    
    query = """
    UNWIND $nodes AS n
    MERGE (node:GraphNode {id: n.id})
    SET node += n
    RETURN count(*)
    """
    tx.run(query, nodes=sanitized)


def _ingest_edges(tx, edges: list[dict]):
    """Create relationships between existing nodes."""
    # Escape edge type to be a valid Cypher identifier
    query = """
    UNWIND $edges AS e
    MATCH (src:GraphNode {id: e.source})
    MATCH (tgt:GraphNode {id: e.target})
    CALL apoc.create.relationship(src, replace(e.type, ' ', '_'), {}, tgt)
    YIELD rel
    RETURN count(rel)
    """
    tx.run(query, edges=edges)


# ── Query helpers ──────────────────────────────────────────────────────────

def search_nodes(query_text: str, limit: int = 20, node_types: Optional[list[str]] = None) -> list[dict]:
    """Full-text search across node label, summary, name, file, type.

    Uses Neo4j's full-text index for relevance scoring (BM25-style).
    Escapes special Lucene characters to avoid syntax errors.
    """
    driver = get_driver()
    # Escape Lucene special chars: + - & | ! ( ) { } [ ] ^ " ~ * ? : \ /
    escaped = query_text
    for ch in r'+-&|!(){}[]^"~*?:\/':
        escaped = escaped.replace(ch, '\\' + ch)
    with driver.session(database=NEO4J_DATABASE) as session:
        if node_types:
            result = session.run(
                """
                CALL db.index.fulltext.queryNodes('nodeSearch', $q, {limit: $limit})
                YIELD node, score
                WHERE ANY(t IN $types WHERE node.type = t)
                RETURN node{.*, _score: score} AS result
                ORDER BY score DESC
                """,
                q=escaped,
                limit=limit,
                types=node_types,
            )
        else:
            result = session.run(
                """
                CALL db.index.fulltext.queryNodes('nodeSearch', $q, {limit: $limit})
                YIELD node, score
                RETURN node{.*, _score: score} AS result
                ORDER BY score DESC
                """,
                q=escaped,
                limit=limit,
            )
        records = list(result)
        return [r["result"] for r in records]


def score_tools_for_task(task_description: str, limit: int = 15) -> list[dict]:
    """Score tool classes against a task description using Cypher graph traversal.

    Uses full-text search on tool summaries, then traverses to get details.
    """
    escaped = task_description
    for ch in r'+-&|!(){}[]^"~*?:\/':
        escaped = escaped.replace(ch, '\\' + ch)
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            """
            CALL db.index.fulltext.queryNodes('toolSearch', $q, {limit: $limit})
            YIELD node, score
            OPTIONAL MATCH (node)<-[:IMPLEMENTS_REQUIRED_METHOD]-(callNode:GraphNode)
            WITH node, score, callNode.summary AS call_summary
            RETURN {
              name: node.name,
              category: node.category,
              summary: node.summary,
              call_summary: call_summary,
              score: round(score, 2)
            } AS tool
            ORDER BY score DESC
            LIMIT $limit
            """,
            q=escaped,
            limit=limit,
        )
        return [r["tool"] for r in result]


def get_tool_catalog() -> dict[str, dict]:
    """Return all tool classes with their metadata."""
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            """
            MATCH (node:GraphNode {type: 'Class'})
            WHERE node.summary IS NOT NULL
            RETURN node{.name, .category, .summary, .file} AS tool
            ORDER BY node.name
            """
        )
        catalog = {}
        for r in result:
            t = r["tool"]
            catalog[t["name"]] = {
                "category": t.get("category"),
                "summary": t.get("summary"),
                "file": t.get("file"),
            }
        return catalog


def get_context_for_task(
    task_description: str,
    include_tools: bool = True,
    include_related_files: bool = True,
    max_tools: int = 10,
    max_related: int = 20,
) -> dict[str, Any]:
    """Build a context bundle for a task — the core dynamic prompt injection function.

    Neo4j best practices used:
    - Full-text index for initial relevance scoring
    - Pattern matching for relationship traversal
    - Parameterized queries throughout
    - Single session for related queries
    """
    escaped = task_description
    for ch in r'+-&|!(){}[]^"~*?:\/':
        escaped = escaped.replace(ch, '\\' + ch)
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        context: dict[str, Any] = {"task": task_description}

        if include_tools:
            tools_result = session.run(
                """
                CALL db.index.fulltext.queryNodes('nodeSearch', $q, {limit: $max_tools})
                YIELD node, score
                WHERE node.type = 'Class' AND node.summary IS NOT NULL
                OPTIONAL MATCH (node)<-[:IMPLEMENTS_REQUIRED_METHOD]-(callNode)
                RETURN {
                  name: node.name,
                  category: node.category,
                  summary: node.summary,
                  call_summary: callNode.summary,
                  score: round(score, 2),
                  file: node.file
                } AS tool
                ORDER BY score DESC
                """,
                q=escaped,
                max_tools=max_tools,
            )
            context["tools"] = [r["tool"] for r in tools_result]

        if include_related_files:
            files_result = session.run(
                """
                CALL db.index.fulltext.queryNodes('nodeSearch', $q, {limit: $max_related})
                YIELD node, score
                WHERE node.type IN ['Class', 'Function', 'File']
                WITH DISTINCT node.file AS file, max(score) AS max_score
                WHERE file IS NOT NULL
                RETURN {file: file, relevance: round(max_score, 2)} AS file_info
                ORDER BY max_score DESC
                LIMIT $max_related
                """,
                q=escaped,
                max_related=max_related,
            )
            context["related_files"] = [r["file_info"] for r in files_result]

        return context


def get_file_context(file_path: str, depth: int = 2) -> dict:
    """Traverse the graph from a file node and return its context.
    
    Returns:
    - file summary and contents (functions, classes)
    - upstream files (this file imports from)
    - downstream files (files that import this one)
    - relationship summaries
    
    Best practices:
    - Pattern matching for CONTAINS and DEPENDS_ON relationships
    - Depth-limited traversal to avoid context bloat
    - Aggregation of summaries at each hop
    """
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        # Find the file node
        file_result = session.run(
            """
            MATCH (f:GraphNode {type: 'File'})
            WHERE f.path = $path
            RETURN f
            """,
            path=file_path,
        )
        file_record = file_result.single()
        if not file_record:
            return {"error": f"File not found: {file_path}"}

        file_node = file_record["f"]

        # Get file contents (functions, classes) via CONTAINS
        contents_result = session.run(
            """
            MATCH (f:GraphNode {type: 'File'})
            WHERE f.path = $path
            MATCH (f)-[:CONTAINS]->(child)
            WHERE child.type IN ['Function', 'Class', 'State', 'Prop']
            RETURN child{.id, .name, .type, .summary, .line_start, .line_end} AS item
            ORDER BY child.type, child.line_start
            """,
            path=file_path,
        )
        contents = [r["item"] for r in contents_result]

        # Get upstream dependencies (files this file imports/depends on)
        upstream_result = session.run(
            """
            MATCH (f:GraphNode {type: 'File'})
            WHERE f.path = $path
            MATCH (f)-[:CONTAINS]->(child)-[:DEPENDS_ON|CALLS*1..$depth]->(other)
            WHERE other.type = 'File' AND other.id <> f.id
            RETURN DISTINCT other{.file, .path, .summary} AS dep,
                   count(*) AS strength
            ORDER BY strength DESC
            """,
            path=file_path,
            depth=depth,
        )
        upstream = [r["dep"] for r in upstream_result]

        # Get downstream dependents (files that depend on this file)
        downstream_result = session.run(
            """
            MATCH (f:GraphNode {type: 'File'})
            WHERE f.path = $path
            MATCH (other:GraphNode {type: 'File'})-[:CONTAINS]->(child)-[:DEPENDS_ON|CALLS*1..$depth]->(fChild)
            WHERE fChild IN [(f)-[:CONTAINS]->(c) | c]
            AND other.id <> f.id
            RETURN DISTINCT other{.file, .path, .summary} AS dep,
                   count(*) AS strength
            ORDER BY strength DESC
            """,
            path=file_path,
            depth=depth,
        )
        downstream = [r["dep"] for r in downstream_result]

        return {
            "file": file_node.get("file") or file_node.get("path", file_path),
            "summary": file_node.get("summary"),
            "language": file_node.get("language"),
            "contents": contents,
            "upstream": upstream,
            "downstream": downstream,
        }


def get_task_graph_context(task_description: str, max_files: int = 5, depth: int = 2) -> dict:
    """Build a graph-aware context bundle for a task.

    Goes beyond simple tool matching — traverses the graph to understand
    file relationships, dependencies, and architecture context.

    Returns:
    - Relevant tools (full-text search)
    - Relevant files with their graph context (traversal)
    - Architecture hints (shared dependencies, common patterns)
    """
    # Escape Lucene special chars for full-text queries
    escaped_q = task_description
    for ch in r'+-&|!(){}[]^"~*?:\/':
        escaped_q = escaped_q.replace(ch, '\\' + ch)

    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        context: dict[str, Any] = {"task": task_description}

        # Step 1: Find relevant files via full-text search
        files_result = session.run(
            """
            CALL db.index.fulltext.queryNodes('nodeSearch', $q, {limit: 20})
            YIELD node, score
            WHERE node.type = 'File'
            RETURN node{.file, .path, .summary, .language} AS f, score
            ORDER BY score DESC
            LIMIT $max_files
            """,
            q=escaped_q,
            max_files=max_files,
        )
        file_nodes = [(r["f"], r["score"]) for r in files_result]

        # Fallback: if no files matched, try direct path matching on keywords
        if not file_nodes:
            fallback = session.run(
                """
                MATCH (f:GraphNode {type: 'File'})
                WHERE any(word IN split(toLower($q), ' ')
                  WHERE size(word) > 2 AND (
                    toLower(coalesce(f.file, f.path, '')) CONTAINS word
                    OR toLower(coalesce(f.summary, '')) CONTAINS word
                  ))
                RETURN f{.file, .path, .summary, .language} AS f, 1.0 AS score
                LIMIT $max_files
                """,
                q=escaped_q,
                max_files=max_files,
            )
            file_nodes = [(r["f"], r["score"]) for r in fallback]

        # Step 2: For each relevant file, traverse its graph context
        enriched_files = []
        for fnode, score in file_nodes:
            file_path = fnode.get("file") or fnode.get("path")
            if not file_path:
                continue

            # Get file contents
            contents_result = session.run(
                """
                MATCH (f:GraphNode {type: 'File'})
                WHERE f.path = $path
                MATCH (f)-[:CONTAINS]->(child)
                WHERE child.type IN ['Function', 'Class']
                RETURN child{.name, .type, .summary} AS item
                ORDER BY child.type, child.line_start
                """,
                path=file_path,
            )
            contents = [r["item"] for r in contents_result]

            # Get dependencies (traverse DEPENDS_ON edges)
            deps_result = session.run(
                """
                MATCH (f:GraphNode {type: 'File'})
                WHERE f.path = $path
                MATCH (f)-[:CONTAINS]->()-[:DEPENDS_ON]->(dep)
                WHERE dep.type IN ['Import', 'DependencyList']
                RETURN dep{.name, .id} AS d
                LIMIT 15
                """,
                path=file_path,
            )
            deps = [r["d"] for r in deps_result]

            # Get files that depend on this file (reverse traversal)
            # Match imports that reference this file's path
            reverse_result = session.run(
                """
                MATCH (f:GraphNode {type: 'File'})
                WHERE f.path = $path
                MATCH (other:GraphNode {type: 'File'})-[:CONTAINS]->(child)-[:DEPENDS_ON]->(dep)
                WHERE dep.type = 'Import'
                  AND (dep.file = f.file OR dep.file = f.path OR coalesce(f.file, f.path) CONTAINS coalesce(dep.file, ''))
                  AND other.id <> f.id
                RETURN DISTINCT other{.file, .path} AS dependent
                LIMIT 10
                """,
                path=file_path,
            )
            dependents = [r["dependent"] for r in reverse_result]

            enriched_files.append({
                "file": file_path,
                "relevance": round(score, 2),
                "summary": fnode.get("summary"),
                "language": fnode.get("language"),
                "contents": contents[:10],  # Cap to avoid bloat
                "dependencies": deps,
                "depended_by": dependents,
            })

        context["files"] = enriched_files

        # Step 3: Get relevant tools from the :Tool island. toolSearch indexes
        # ONLY real tool nodes, so there's no co-ranking with File/Function nodes
        # and no non-tool Class imposters — a plain limit is correct here.
        tools_result = session.run(
            """
            CALL db.index.fulltext.queryNodes('toolSearch', $q, {limit: 8})
            YIELD node, score
            OPTIONAL MATCH (node)<-[:IMPLEMENTS_REQUIRED_METHOD]-(callNode)
            RETURN {
              name: node.name,
              category: node.category,
              summary: node.summary,
              call_summary: callNode.summary,
              score: round(score, 2),
              file: node.file
            } AS tool
            ORDER BY score DESC
            """,
            q=escaped_q,
        )
        context["tools"] = [r["tool"] for r in tools_result]

        return context


# ── New traversal mechanisms ─────────────────────────────────────────────

def get_directory_tree(dir_path: str = None) -> list[dict]:
    """Return the Root → Directory → Directory → File hierarchy as a flat list
    with parent references, suitable for building a tree client-side.

    If dir_path is given, returns only the subtree rooted at that path.
    Otherwise returns the full tree from root.
    """
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        if dir_path:
            result = session.run(
                """
                MATCH (root:GraphNode {type: 'Root'})
                MATCH path = (root)-[:CONTAINS*0..]->(n)
                WHERE n.type IN ['Root', 'Directory', 'File']
                  AND n.path STARTS WITH $dir_path
                RETURN n{.id, .name, .type, .path} AS node,
                       relationships(path) AS rels
                ORDER BY n.path
                """,
                dir_path=dir_path,
            )
        else:
            result = session.run(
                """
                MATCH (root:GraphNode {type: 'Root'})
                MATCH path = (root)-[:CONTAINS*0..]->(n)
                WHERE n.type IN ['Root', 'Directory', 'File']
                RETURN n{.id, .name, .type, .path} AS node
                ORDER BY n.path
                """,
            )
        nodes = []
        seen = set()
        for r in result:
            n = r["node"]
            if n["id"] not in seen:
                seen.add(n["id"])
                nodes.append(n)
        return nodes


def trace_call_chain(node_id: str, direction: str = "downstream", max_depth: int = 3) -> dict:
    """Follow CALLS edges from or to a function.

    direction='downstream' → what this function calls (dependencies)
    direction='upstream'   → who calls this function (dependents)

    Returns nested call tree with summaries.
    """
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        # Neo4j doesn't allow $param in variable-length path bounds, so interpolate safely
        depth = int(max_depth)
        if direction == "downstream":
            query = f"""
            MATCH (start:GraphNode {{id: $node_id}})
            MATCH path = (start)-[:CALLS*0..{depth}]->(target)
            WHERE target.type IN ['Function', 'Class']
            RETURN target{{.id, .name, .type, .file, .summary, .line_start, .line_end}} AS node,
                   length(path) AS hops
            ORDER BY hops, target.file, target.line_start
            """
        else:
            query = f"""
            MATCH (start:GraphNode {{id: $node_id}})
            MATCH path = (target)-[:CALLS*0..{depth}]->(start)
            WHERE target.type IN ['Function', 'Class']
            RETURN target{{.id, .name, .type, .file, .summary, .line_start, .line_end}} AS node,
                   length(path) AS hops
            ORDER BY hops, target.file, target.line_start
            """
        result = session.run(query, node_id=node_id)
        nodes = []
        seen = set()
        for r in result:
            n = r["node"]
            if n["id"] not in seen:
                seen.add(n["id"])
                n["_hops"] = r["hops"]
                nodes.append(n)
        return {"node_id": node_id, "direction": direction, "chain": nodes}


def get_tool_capability_tree(category: str = None) -> list[dict]:
    """Return tool classes with their call method summaries.

    If category is given, filter to that category only.
    Traverses: Class -(IMPLEMENTS_REQUIRED_METHOD)-> function::qwen_agent::call
    """
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        where_clause = "WHERE tool.type = 'Class'"
        params: dict = {}
        if category:
            where_clause += " AND tool.category = $category"
            params["category"] = category

        result = session.run(
            f"""
            MATCH (tool:GraphNode)
            {where_clause}
            OPTIONAL MATCH (tool)<-[:IMPLEMENTS_REQUIRED_METHOD]-(call:GraphNode)
            RETURN {{
              name: tool.name,
              category: tool.category,
              summary: tool.summary,
              file: tool.file,
              call_summary: call.summary
            }} AS tool
            ORDER BY tool.name
            """,
            **params,
        )
        return [r["tool"] for r in result]


def find_state_users(state_type: str) -> dict:
    """Given a State node name (e.g. 'Message'), find all functions that use it
    via TRACKS edges, plus their Prop children.
    """
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        # Find the state node
        state_result = session.run(
            """
            MATCH (s:GraphNode {type: 'State', name: $state_type})
            RETURN s{.id, .name, .file, .line_start, .line_end} AS state
            LIMIT 1
            """,
            state_type=state_type,
        )
        state_rec = state_result.single()
        if not state_rec:
            return {"error": f"State '{state_type}' not found"}

        state_node = state_rec["state"]

        # Find functions that track this state
        users_result = session.run(
            """
            MATCH (func:GraphNode {type: 'Function'})-[:TRACKS]->(s:GraphNode {type: 'State', name: $state_type})
            RETURN func{.id, .name, .file, .summary} AS func
            """,
            state_type=state_type,
        )
        users = [r["func"] for r in users_result]

        # Find props tracked by this state
        props_result = session.run(
            """
            MATCH (s:GraphNode {type: 'State', name: $state_type})-[:TRACKS]->(p:GraphNode {type: 'Prop'})
            RETURN p{.id, .name, .prop_type} AS prop
            """,
            state_type=state_type,
        )
        props = [r["prop"] for r in props_result]

        return {"state": state_node, "used_by": users, "props": props}


def find_impact_zone(node_id: str) -> dict:
    """What breaks if this node changes. Union of:
    - Reverse CALLS (who calls this function)
    - Reverse TRACKS (who tracks this state)
    - Same-file siblings (co-located code likely affected)
    """
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        # Get the target node
        node_result = session.run(
            """
            MATCH (n:GraphNode {id: $node_id})
            RETURN n{.id, .name, .type, .file} AS node
            """,
            node_id=node_id,
        )
        node_rec = node_result.single()
        if not node_rec:
            return {"error": f"Node '{node_id}' not found"}

        target = node_rec["node"]
        target_type = target.get("type", "")
        target_file = target.get("file") or target.get("path", "")

        # Reverse CALLS (only for Function/Class targets)
        callers = []
        if target_type in ("Function", "Class"):
            callers_result = session.run(
                """
                MATCH (caller:GraphNode {type: 'Function'})-[:CALLS]->(target:GraphNode {id: $node_id})
                RETURN caller{.id, .name, .file, .summary} AS caller
                """,
                node_id=node_id,
            )
            callers = [r["caller"] for r in callers_result]

        # Reverse TRACKS
        trackers_result = session.run(
            """
            MATCH (tracker:GraphNode)-[:TRACKS]->(target:GraphNode {id: $node_id})
            RETURN tracker{.id, .name, .type, .file} AS tracker
            """,
            node_id=node_id,
        )
        trackers = [r["tracker"] for r in trackers_result]

        # Same-file siblings — traverse from file node
        siblings = []
        if target_file:
            siblings_result = session.run(
                """
                MATCH (file:GraphNode {type: 'File'})
                WHERE file.path = $file_path OR file.file = $file_path
                MATCH (file)-[:CONTAINS]->(sibling)
                WHERE sibling.type IN ['Function', 'Class', 'State']
                  AND sibling.id <> $node_id
                RETURN sibling{.id, .name, .type, .summary} AS sibling
                LIMIT 20
                """,
                file_path=target_file,
                node_id=node_id,
            )
            siblings = [r["sibling"] for r in siblings_result]

        return {
            "target": target,
            "called_by": callers,
            "tracked_by": trackers,
            "siblings": siblings,
        }


# ── Visualization ──────────────────────────────────────────────────────────

def get_viz_data(filter_type: Optional[str] = None, depth: int = 1) -> dict:
    """Return visualization data from Neo4j (replaces get_viz_data from graph_query)."""
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        if filter_type:
            result = session.run(
                """
                MATCH (n:GraphNode {type: $type})
                WITH collect(n) AS seeds
                CALL {
                  WITH seeds
                  UNWIND seeds AS seed
                  MATCH path = (seed)-[*1..$depth]-(neighbor)
                  RETURN DISTINCT neighbor
                }
                WITH seeds + collect(DISTINCT neighbor) AS all_nodes
                UNWIND all_nodes AS node
                WITH DISTINCT node
                RETURN node{.*} AS n
                """,
                type=filter_type,
                depth=depth,
            )
            nodes = [r["n"] for r in result]
            node_ids = {n["id"] for n in nodes}
            
            # Get edges between these nodes
            edges_result = session.run(
                """
                MATCH (src)-[rel]->(tgt)
                WHERE src.id IN $ids AND tgt.id IN $ids
                RETURN {
                  id: src.id + '->' + tgt.id,
                  source: src.id,
                  target: tgt.id,
                  type: type(rel)
                } AS e
                """,
                ids=list(node_ids),
            )
            edges = [r["e"] for r in edges_result]
        else:
            nodes_result = session.run("MATCH (n:GraphNode) RETURN n{.*} AS n")
            nodes = [r["n"] for r in nodes_result]
            edges_result = session.run(
                """
                MATCH (src)-[rel]->(tgt)
                RETURN {
                  id: src.id + '->' + tgt.id,
                  source: src.id,
                  target: tgt.id,
                  type: type(rel)
                } AS e
                """
            )
            edges = [r["e"] for r in edges_result]

    return {"nodes": nodes, "edges": edges}


def clear_database():
    """Delete all nodes and relationships. Use with care."""
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    log.info("Neo4j database cleared")
