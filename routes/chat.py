"""Chat streaming and context summarization routes."""

import json
import logging
import queue
import threading
import uuid
import re
from datetime import datetime, timezone

from services.logging_setup import set_correlation_id

log = logging.getLogger(__name__)

import json5
from flask import Blueprint, Response, g, jsonify, request, stream_with_context
from flask_login import current_user, login_required
from qwen_agent.agents.fncall_agent import FnCallAgent
from qwen_agent.tools.base import TOOL_REGISTRY as QW_TOOL_REGISTRY

from auth.conversation_tasks import ConversationTask
from auth.conversations import Conversation, ConversationMessage
from auth.db import get_db
import subprocess
from config import (
    LLAMA_ARG_CTX_SIZE,
    LLAMA_PORT,
    LLAMA_SERVER_URL,
    qwen_llm_cfg,
)
from context import (
    build_history,
    serialize_assistant_message,
    serialize_tool_result,
    serialize_user_message,
)
from agents.agent_main import MAIN_SYSTEM_PROMPT, MAIN_TASK_TOOLS, build_main_agent
from agents.agent_summary import summarize as summarize_transcript
from agents.agent_taskmgr import run_taskmgr
from pipeline.workflow_groups import TOOL_REF
from tools.web import _dl_jobs, _dl_lock
from services.llama import (
    MODEL_SWAP_LOCK,
    kill_llama_server,
    loaded_model_id,
    spawn_llama_server,
)
from tools.web import _strip_html_noise


def _registered_name(graph_name: str) -> str:
    """Translate a Neo4j tool node name to the qwen-agent registered tool name.

    The graph stores tools by Python CLASS name (e.g. 'BrowserClickTool'); the
    qwen-agent registry is keyed by the tool's `name` attribute (e.g. 'www_click').
    A graph_name that is already a registry key is returned unchanged.
    """
    if graph_name in QW_TOOL_REGISTRY:
        return graph_name
    return _CLASS_TO_TOOL_NAME.get(graph_name, graph_name)


# class.__name__ → registered tool name, built once from the live registry.
_CLASS_TO_TOOL_NAME = {
    cls.__name__: reg_name for reg_name, cls in QW_TOOL_REGISTRY.items()
}


# Neo4j context injection — dynamic tool relevance via system prompt
def _build_neo4j_tool_context(task_description: str) -> tuple[str, list[str]]:
    """Query Neo4j for relevant tools AND trigger graph traversals.

    Returns (prompt_block, tool_names) where:
    - prompt_block is a structured context string injected into the system prompt:
      relevant tools, relevant files + deps, call chains, state context,
      impact zone, tool capabilities.
    - tool_names are the EXACT tool names surfaced in the "RELEVANT TOOLS" block,
      so the caller can place the same set in the agent's function_list. This is
      the single source of truth: a tool described in the prompt is also callable.

    Returns ("", []) if Neo4j is unavailable (graceful fallback).
    """
    surfaced_tools: list[str] = []
    try:
        from services.neo4j_context import (
            get_task_graph_context,
            get_directory_tree,
            trace_call_chain,
            get_tool_capability_tree,
            find_state_users,
            find_impact_zone,
        )

        ctx = get_task_graph_context(task_description, max_files=5, depth=2)
        parts = []

        # Tools section — only surface nodes that map to a callable registered
        # tool, so the model is never shown a tool it cannot call.
        tools = ctx.get("tools", [])
        if tools:
            tool_lines = []
            for t in tools:
                name = _registered_name(t.get("name", ""))
                if name not in QW_TOOL_REGISTRY:
                    continue
                summary = (t.get("summary") or "")[:150]
                category = t.get("category", "")
                tool_lines.append(f"- {name} ({category}): {summary}")
                surfaced_tools.append(name)
            if tool_lines:
                parts.append(
                    "\n\n## RELEVANT TOOLS FOR THIS TASK\n" + "\n".join(tool_lines)
                )

        # File graph context section
        files = ctx.get("files", [])
        if files:
            file_parts = ["\n\n## RELEVANT FILES AND RELATIONSHIPS\n"]
            for f in files:
                fpath = f.get("file", "")
                summary = f.get("summary", "")
                relevance = f.get("relevance", 0)
                file_parts.append(f"\n### `{fpath}` (relevance: {relevance})")
                if summary:
                    file_parts.append(f"Summary: {summary[:150]}")

                # Contents
                contents = f.get("contents", [])
                if contents:
                    items = [
                        f"  - {c['type']} {c['name']}"
                        + (f": {c.get('summary', '')[:80]}" if c.get("summary") else "")
                        for c in contents[:6]
                    ]
                    file_parts.append("Contents:\n" + "\n".join(items))

                # Dependencies
                deps = f.get("dependencies", [])
                if deps:
                    dep_names = [d.get("name", d.get("id", "")) for d in deps[:5]]
                    file_parts.append(f"Depends on: {', '.join(dep_names)}")

                # Dependents
                dependents = f.get("depended_by", [])
                if dependents:
                    dep_paths = [
                        d.get("file", d.get("path", "")) for d in dependents[:5]
                    ]
                    file_parts.append(f"Used by: {', '.join(dep_paths)}")

            parts.append("\n".join(file_parts))

        # Trigger-based traversals
        msg_lower = task_description.lower()

        # --- Call chain: detect function/class references ---
        # Patterns: "function X", "X function", "class X", "def X", "in X.py::name"
        import re

        func_matches = re.findall(
            r"(?:function|class|def|fn)\s+([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)", msg_lower
        )
        func_matches += re.findall(
            r"([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\s+(?:function|class|method)\b",
            msg_lower,
        )
        file_func_matches = re.findall(
            r"([a-zA-Z_/][a-zA-Z0-9_/]*\.(?:py|ts|tsx|js))\s*::\s*([a-zA-Z_]\w*)",
            task_description,
        )
        if func_matches or file_func_matches:
            chain_parts = []
            for match in func_matches:
                # Try to find in Neo4j by name
                name_parts = match.split(".")
                func_name = name_parts[-1]
                from services.neo4j_context import search_nodes

                results = search_nodes(
                    func_name, limit=3, node_types=["Function", "Class"]
                )
                if results:
                    best = results[0]
                    chain = trace_call_chain(
                        best["id"], direction="downstream", max_depth=2
                    )
                    if chain["chain"]:
                        chain_lines = [
                            f"  {c['_hops']}h: {c['name']} ({c['type']}) — {c.get('summary', '')[:100] or '(no summary)'}"
                            for c in chain["chain"][:8]
                        ]
                        chain_parts.append(
                            f"### {best['name']} ({best['file']})\n"
                            + "\n".join(chain_lines)
                        )
            for fp, fname in file_func_matches:
                results = search_nodes(fname, limit=3, node_types=["Function"])
                if results:
                    best = results[0]
                    chain = trace_call_chain(
                        best["id"], direction="downstream", max_depth=2
                    )
                    if chain["chain"]:
                        chain_lines = [
                            f"  {c['_hops']}h: {c['name']} ({c['type']}) — {c.get('summary', '')[:100] or '(no summary)'}"
                            for c in chain["chain"][:8]
                        ]
                        chain_parts.append(
                            f"### {best['name']} ({best['file']})\n"
                            + "\n".join(chain_lines)
                        )
            if chain_parts:
                parts.append("\n\n## CALL CHAINS\n" + "\n".join(chain_parts))

        # --- State context: detect useState/State references ---
        state_matches = re.findall(r"\b([A-Z][a-zA-Z]*State)\b", task_description)
        state_matches += re.findall(
            r"(?:state|useState|hook)\s*[\(<]?\s*([A-Z][a-zA-Z]*\w*)\b", msg_lower
        )
        if state_matches:
            state_parts = []
            for st_name in set(state_matches):
                result = find_state_users(st_name)
                if "error" not in result:
                    s = result["state"]
                    users = result.get("used_by", [])
                    props = result.get("props", [])
                    lines = [f"  State: {s['name']} in {s['file']}"]
                    if users:
                        lines.append(
                            f"  Used by: {', '.join(u['name'] for u in users[:5])}"
                        )
                    if props:
                        lines.append(
                            f"  Props: {', '.join(p['name'] for p in props[:8])}"
                        )
                    state_parts.append("\n".join(lines))
            if state_parts:
                parts.append("\n\n## STATE CONTEXT\n" + "\n".join(state_parts))

        # --- Impact zone: detect change/modify/refactor language ---
        impact_triggers = [
            "change",
            "modify",
            "refactor",
            "update",
            "remove",
            "delete",
            "move",
            "fix",
            "affect",
            "break",
        ]
        if any(t in msg_lower for t in impact_triggers):
            file_refs = re.findall(
                r"`?([a-zA-Z_/][a-zA-Z0-9_/]*\.(?:py|ts|tsx|js))`?", task_description
            )
            if file_refs:
                from services.neo4j_context import search_nodes

                for fref in file_refs:
                    results = search_nodes(fref, limit=3, node_types=["File"])
                    if results:
                        # File found — get its first Function/Class child for impact
                        file_id = results[0]["id"]
                        file_path = results[0].get("path", "")
                        from services.neo4j_context import get_driver, NEO4J_DATABASE

                        driver = get_driver()
                        with driver.session(database=NEO4J_DATABASE) as session:
                            child_result = session.run(
                                """
                                MATCH (f:GraphNode {id: $file_id})-[:CONTAINS]->(child)
                                WHERE child.type IN ['Function', 'Class'] AND child.summary IS NOT NULL
                                RETURN child{.id, .name, .type, .file, .summary} AS c
                                LIMIT 1
                                """,
                                file_id=file_id,
                            )
                            child_rec = child_result.single()
                            if child_rec:
                                impact = find_impact_zone(child_rec["c"]["id"])
                            else:
                                # Fallback: use file node itself
                                impact = find_impact_zone(file_id)
                        if "error" not in impact:
                            tgt = impact["target"]
                            lines = [
                                f"  Target: {tgt['name']} ({tgt['type']}) in {tgt['file']}"
                            ]
                            if impact["called_by"]:
                                lines.append(
                                    f"  Called by: {', '.join(c['name'] for c in impact['called_by'][:5])}"
                                )
                            if impact["tracked_by"]:
                                lines.append(
                                    f"  Tracked by: {', '.join(t['name'] for t in impact['tracked_by'][:5])}"
                                )
                            if impact["siblings"]:
                                lines.append(
                                    f"  Siblings ({len(impact['siblings'])}): {', '.join(s['name'] for s in impact['siblings'][:8])}"
                                )
                            parts.append("\n\n## IMPACT ZONE\n" + "\n".join(lines))
                            break
                    else:
                        basename = (
                            fref.split("/")[-1]
                            .replace(".py", "")
                            .replace(".ts", "")
                            .replace(".tsx", "")
                        )
                        results = search_nodes(
                            basename, limit=5, node_types=["Function", "Class"]
                        )
                        if results:
                            impact = find_impact_zone(results[0]["id"])
                            if "error" not in impact:
                                tgt = impact["target"]
                                lines = [
                                    f"  Target: {tgt['name']} ({tgt['type']}) in {tgt['file']}"
                                ]
                                if impact["called_by"]:
                                    lines.append(
                                        f"  Called by: {', '.join(c['name'] for c in impact['called_by'][:5])}"
                                    )
                                if impact["tracked_by"]:
                                    lines.append(
                                        f"  Tracked by: {', '.join(t['name'] for t in impact['tracked_by'][:5])}"
                                    )
                                if impact["siblings"]:
                                    lines.append(
                                        f"  Siblings ({len(impact['siblings'])}): {', '.join(s['name'] for s in impact['siblings'][:8])}"
                                    )
                                parts.append("\n\n## IMPACT ZONE\n" + "\n".join(lines))
                                break

        # --- Tool capabilities: detect tool category mentions ---
        cat_keywords = {
            "web": ["web", "browse", "scrape", "fetch", "page", "cookie"],
            "khan": ["khan", "course", "lesson", "education"],
            "ecommerce": ["product", "shop", "ecommerce", "e-commerce", "buy"],
            "onlyfans": ["onlyfans", "of_", "creator"],
            "torrent": ["torrent", "bt_", "download", "magnet"],
            "filesystem": ["file", "dir", "read", "write", "search"],
            "accounting": ["accounting", "ledger", "invoice", "transaction", "fa_"],
            "exploit": [
                "exploit",
                "vuln",
                "scan",
                "attack",
                "pentest",
                "spawn",
                "payload",
                "map",
                "vulnerability",
                "hacking",
                "open ports",
                "ipcam",
                "nmap",
                "expose",
                "exposed port",
            ],
            "bug_bounty": [
                "bug bounty",
                "h1",
                "hackerone",
                "disclosure",
                "hack",
                "bounty",
                "ethical hacking",
                "hacking",
            ],
            "vision": ["vision", "image", "describe", "see"],
            "jobs": [
                "job",
                "posting",
                "listing",
                "board",
                "resume",
                "unemployment",
                "employment",
                "company",
                "career",
            ],
        }
        detected_cats = set()
        for cat, keywords in cat_keywords.items():
            if any(k in msg_lower for k in keywords):
                detected_cats.add(cat)
        if detected_cats:
            tool_parts = []
            for cat in sorted(detected_cats):
                tools = get_tool_capability_tree(category=cat)
                if tools:
                    lines = [f"\n### {cat.upper()} tools"]
                    for t in tools[:5]:
                        reg_name = _registered_name(t.get("name", ""))
                        if reg_name not in QW_TOOL_REGISTRY:
                            continue
                        lines.append(f"- {reg_name}: {t.get('summary', '')[:120]}")
                        surfaced_tools.append(reg_name)
                    if len(lines) > 1:
                        tool_parts.append("\n".join(lines))
            if tool_parts:
                parts.append("\n\n## TOOL CAPABILITIES\n" + "\n".join(tool_parts))

        return "".join(parts), list(dict.fromkeys(surfaced_tools))
    except Exception:
        return "", []


chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


class DynamicAssistant(FnCallAgent):
    """FnCallAgent that passes all registered tools to the model."""

    def __init__(self, *args, conv_id: str = "", **kwargs):
        self._conv_id = conv_id
        super().__init__(*args, **kwargs)


def _llama_error_msg(exc: Exception) -> str:
    """Walk the exception chain and return a human-readable llama-server error."""
    # Collect every exception in the cause chain
    chain, seen = [], set()
    node = exc
    while node is not None and id(node) not in seen:
        chain.append(node)
        seen.add(id(node))
        node = node.__cause__ or (
            node.__context__ if not node.__suppress_context__ else None
        )

    def _str(e):
        return str(e).lower()

    full = " | ".join(_str(e) for e in chain)

    # Connection refused — nothing on that port
    if "connection refused" in full or "errno 111" in full or "[errno 111]" in full:
        return f"No llama server on port {LLAMA_PORT} — process DOA or wrong port"

    # Unreachable host
    if "errno 101" in full or "network is unreachable" in full:
        return f"Network unreachable reaching llama server at {LLAMA_SERVER_URL}"

    # DNS / name resolution
    if "name or service not known" in full or "nodename nor servname" in full:
        return f"Cannot resolve llama server host in {LLAMA_SERVER_URL}"

    # Timeout
    if "timeout" in full or "timed out" in full:
        return f"Llama server at {LLAMA_SERVER_URL} timed out — still loading?"

    # HTTP 404 — model alias not registered
    if "404" in full or "not found" in full:
        return (
            f"Model not found on llama server — alias not loaded on port {LLAMA_PORT}"
        )

    # HTTP 400 — bad request (often context overflow)
    if "400" in full:
        if "context" in full or "tokens" in full:
            return "Input exceeds model context window"
        return (
            f"Llama server rejected the request (HTTP 400): check model and parameters"
        )

    # HTTP 503 / overloaded
    if "503" in full or "service unavailable" in full:
        return f"Llama server on port {LLAMA_PORT} is busy or overloaded"

    # Generic connection error
    if "connection" in full and "error" in full:
        return f"Cannot connect to llama server at {LLAMA_SERVER_URL}"

    return f"Llama server error: {exc}"


def _clean_tool_result(result_str: str) -> str:
    """Backstop: strip HTML noise from any unexpected raw-HTML tool results."""
    if "<html" in result_str[:500].lower() or "<!doctype" in result_str[:500].lower():
        return _strip_html_noise(result_str)
    return result_str


def _unwrap_mcp_call(tool_args: str):
    """Resolve the real tool wrapped inside an mcp_call_tool call.

    Returns (real_name, params):
      - (name, params) when the wrapped tool_name is present and parseable.
      - ("mcp_call_tool", {}) when args are fully parseable but carry no
        tool_name (a genuine bare call).
      - (None, None) when args are still streaming in and can't be parsed yet,
        signalling the caller to defer emitting until the next yield.
    """
    raw = (tool_args or "").strip()
    try:
        parsed = json5.loads(raw or "{}")
    except Exception:
        return None, None  # incomplete JSON — args still arriving

    real = (parsed.get("tool_name") or "").strip()
    if real:
        return real, (parsed.get("parameters") or {})
    # Parsed cleanly but no usable tool_name. If the key is present-but-empty
    # the name is still streaming, so keep waiting. An empty/"{}" payload is
    # likewise pre-stream. Otherwise it's a genuine bare mcp_call_tool.
    if "tool_name" in parsed or raw in ("", "{}"):
        return None, None
    return "mcp_call_tool", {}


_HEARTBEAT = object()


def _tick_iterator(
    iterable,
    tick_seconds: float = 20.0,
    g_vals: dict = None,
):
    """Yield items from a blocking iterable, injecting _HEARTBEAT on idle gaps.

    Needed because qwen-agent's generator blocks while tools run synchronously
    (e.g., multi-MB downloads). Without periodic output, the frontend's 90s
    stale-stream watchdog false-positive-cancels healthy long tool calls.

    Tools inside the iterable may touch `flask.g` / request-scoped state, so the
    pump thread must inherit the caller's request context via
    `copy_current_request_context`. However, copy_current_request_context pushes
    a fresh AppContext (and thus a blank g) in the new thread — g_vals are
    re-applied after the context is entered so tools can read them.
    """
    from flask import copy_current_request_context, g as _g

    q: queue.Queue = queue.Queue()
    _DONE = object()
    _g_vals = g_vals or {}

    @copy_current_request_context
    def _pump():
        for k, v in _g_vals.items():
            setattr(_g, k, v)
        try:
            for item in iterable:
                q.put(("item", item))
        except BaseException as e:
            q.put(("err", e))
        finally:
            q.put(("done", _DONE))

    threading.Thread(target=_pump, daemon=True).start()

    while True:
        try:
            kind, payload = q.get(timeout=tick_seconds)
        except queue.Empty:
            yield _HEARTBEAT
            continue
        if kind == "done":
            return
        if kind == "err":
            raise payload
        yield payload


def _estimate_tokens(
    messages: list, system_prompt: str = "", active_tools: list = None
) -> int:
    try:
        from context.tokens import count_tokens, TOKENS_PER_TOOL

        # Prepend system message so its tokens are included
        all_msgs = (
            [{"role": "system", "content": system_prompt}] if system_prompt else []
        ) + list(messages)
        base = count_tokens(all_msgs)
        # Tool schema tokens: qwen-agent injects these into the context but they're not in messages
        tool_overhead = len(active_tools or []) * TOKENS_PER_TOOL
        return base + tool_overhead
    except Exception as e:
        logging.getLogger(__name__).debug(
            "Token counter unavailable — falling back to char/4 estimate: %s", e
        )
        return sum(len(str(m.get("content", ""))) for m in messages) // 4


def _existing_task_dicts(db, conversation_id: str) -> list[dict]:
    rows = (
        db.query(ConversationTask)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationTask.created_at.asc())
        .all()
    )
    return [{"id": r.id, "title": r.title, "status": r.status} for r in rows]


def _run_taskmgr_safe(conversation_id: str, user_msg: str, db) -> None:
    """Run the task-manager agent to build/refresh the list. Never raises —
    a taskmgr failure must not block the main chat turn."""
    if not conversation_id:
        return
    try:
        existing = _existing_task_dicts(db, conversation_id)
        run_taskmgr(conversation_id, user_msg, existing)
        db.expire_all()  # main agent's later query sees taskmgr's writes
    except Exception as taskmgr_err:
        log.warning("task-manager run failed (continuing without it): %s", taskmgr_err)


def _review_done_claims(conversation_id: str, done_ids: list[str], evidence: str,
                        db) -> list[dict]:
    """Review each tl_done claim with the task-manager agent.

    Branch 1 (always): the reviewer judges done-ness from `evidence`.
      - agrees   → task stays marked done (tl_done already set it).
      - disagrees→ task reverted to pending and returned for human review.

    Returns the disputed tasks [{id, title, reason}] so the caller can hand them
    to the user (Branch 2). Never raises.
    """
    from agents.agent_taskmgr import review_task_completion

    disputed: list[dict] = []
    if not conversation_id or not done_ids:
        return disputed
    try:
        rows = {
            r.id: r
            for r in db.query(ConversationTask)
            .filter_by(conversation_id=conversation_id)
            .all()
        }
        for task_id in done_ids:
            row = rows.get(task_id)
            if not row:
                continue
            verdict = review_task_completion(conversation_id, row.title, evidence)
            if verdict["agree"]:
                continue
            row.status = "pending"  # revert until the human ratifies
            disputed.append({"id": row.id, "title": row.title, "reason": verdict["reason"]})
        if disputed:
            db.commit()
    except Exception as review_err:
        log.warning("done-claim review failed (leaving tasks as-is): %s", review_err)
    return disputed


@chat_bp.route("/stream", methods=["POST"])
@login_required
def chat_stream():
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    conversation_id = data.get("conversation_id")
    if not user_msg:
        return jsonify({"error": "message required"}), 400
    if not conversation_id:
        logging.getLogger(__name__).info(
            "chat_stream: no conversation_id supplied — a new conversation will be created"
        )

    prefs = current_user.preferences or {}
    model_name = prefs.get("model")

    # Capture user identity as plain scalars now, while the session is live.
    # generate() streams lazily (stream_with_context) and its body runs after
    # the request session may have closed — touching current_user there raises
    # DetachedInstanceError. fs tools need these on the pump thread (blank g).
    fs_user_id = current_user.id
    fs_user_role = getattr(current_user, "role", None)

    if not model_name:
        return jsonify({"error": "No model selected"}), 400

    set_correlation_id(f"chat-{uuid.uuid4().hex[:8]}")
    log.info(
        "chat_start: msg=%r conv_id=%s model=%s",
        user_msg[:50],
        conversation_id,
        model_name,
    )

    db = get_db()

    if conversation_id:
        conv = (
            db.query(Conversation)
            .filter_by(id=conversation_id, user_id=current_user.id)
            .first()
        )
        if not conv:
            return jsonify({"error": "Conversation not found"}), 404
    else:
        conv = Conversation(
            user_id=current_user.id,
            title=user_msg[:40],
            model=model_name,
        )
        db.add(conv)
        db.commit()
        conversation_id = conv.id

    g.conversation_id = conversation_id

    db_messages = (
        db.query(ConversationMessage)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationMessage.created_at.asc())
        .all()
    )
    history_rows = [
        {"role": m.role, "content": m.content, "tool_calls": m.tool_calls or []}
        for m in db_messages
    ]
    history = build_history(history_rows)

    # Inline compaction: at the start of the turn (no stream active yet, so no
    # write conflict), if the would-be prompt crosses the budget, fold old
    # messages into conv.running_summary and send [summary] + recent instead of
    # the full history. Non-destructive — db_messages stay intact. The full-
    # history path leaves the main agent's prompt cache warm; only crossing the
    # threshold changes the prefix.
    from context.compaction import needs_compaction, fold_old_messages, compacted_history

    pending = history + [{"role": "user", "content": user_msg}]
    if db_messages and needs_compaction(_estimate_tokens(pending), LLAMA_ARG_CTX_SIZE):
        try:
            recent_rows = fold_old_messages(conv, db_messages)
            db.commit()
            # Replace full history with [summary] + recent. The real user message
            # is still appended downstream (qwen_messages = history + [user msg]).
            history = compacted_history(conv.running_summary, recent_rows)
        except Exception as compaction_err:
            db.rollback()
            logging.getLogger(__name__).warning(
                "Inline compaction failed, sending full history: %s", compaction_err
            )

    # Resolve only the tools relevant to this task — not the full registry.
    # Neo4j scores tools against the task; falls back to LLM-based routing.
    # Always include task-management and introspection tools.
    # Main agent reads (tl_ref) and completes (tl_done) tasks only — the
    # task-manager agent owns adds. MAIN_TASK_TOOLS == ["tl_ref", "tl_done"].
    # No list_tools: tool relevance is driven entirely by the Neo4j graph, which
    # injects the relevant tools into the prompt AND exposes the same set here.
    _ALWAYS_TOOLS = [
        *MAIN_TASK_TOOLS,
        "get_params",
        "mcp_init_conn",
        "mcp_call_tool",
    ]

    # Single Neo4j pass: the tools described in the injected prompt block are the
    # exact tools placed in function_list, so anything the model is told about is
    # actually callable (fixes "Tool X does not exists.").
    neo4j_ctx, neo4j_tools = _build_neo4j_tool_context(user_msg[:500])

    def _resolve_tools(surfaced: list[str]) -> list[str]:
        names = [n for n in surfaced if n in QW_TOOL_REGISTRY]
        if not names:
            from tools.native import _route_tools
            names = _route_tools(user_msg[:500])
        return list(dict.fromkeys(_ALWAYS_TOOLS + names))

    function_list = _resolve_tools(neo4j_tools)

    # Task-manager agent is the FIRST receiver of the user message: it builds /
    # refreshes the task list (flat root-edge-node graph → ConversationTask) the
    # main agent will work off of. Runs synchronously before the main stream.
    _run_taskmgr_safe(conversation_id, user_msg, db)

    conv_tasks = (
        db.query(ConversationTask)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationTask.created_at.asc())
        .all()
    )
    task_augmentation = ""

    if conv_tasks:
        unnotified = [t for t in conv_tasks if t.notified_at is None]
        if unnotified:
            if len(unnotified) == len(conv_tasks):
                lines = [
                    f"  {i}. [{t.status}] id={t.id} — {t.title}"
                    for i, t in enumerate(conv_tasks, 1)
                ]
                task_augmentation = "\n\n[TASK LIST]\n" + "\n".join(lines)
            else:
                lines = [f"[Task Added] id={t.id} — {t.title}" for t in unnotified]
                task_augmentation = "\n\n" + "\n".join(lines)
            now = datetime.now(timezone.utc)
            for t in unnotified:
                t.notified_at = now
            db.commit()

    def generate():
        full_response = ""
        ordered_messages = []

        yield json.dumps({"conversation_id": conversation_id}) + "\n"

        # Inject the Neo4j-derived tool context (built once above) so the prompt
        # describes exactly the tools present in function_list.
        system_prompt = MAIN_SYSTEM_PROMPT + neo4j_ctx if neo4j_ctx else MAIN_SYSTEM_PROMPT
        augmented_msg = user_msg + task_augmentation

        assistant = build_main_agent(
            DynamicAssistant,
            llm=qwen_llm_cfg(model_name),
            function_list=function_list,
            system_message=system_prompt,
            conv_id=conversation_id or "",
        )

        qwen_messages = history + [{"role": "user", "content": augmented_msg}]

        context_pct = round(
            min(
                _estimate_tokens(qwen_messages, system_prompt, function_list)
                / LLAMA_ARG_CTX_SIZE
                * 100,
                100,
            ),
            1,
        )
        yield json.dumps({"context_pct": context_pct}) + "\n"

        def _log(msg):
            log.info("%s", msg)

        cancelled = False
        # tl_done claims this turn → reviewed at stream close. {task_id: title}
        done_claims: dict[str, str] = {}
        # Rolling evidence the reviewer reads to judge done-ness.
        evidence_log: list[str] = []
        # FIFO of real tool names for mcp_call_tool unwrap — push on call, pop on result.
        mcp_real_names: list[str] = []
        try:
            prev_content = ""
            seen_fn_count = 0

            for responses in _tick_iterator(
                assistant.run(messages=qwen_messages),
                g_vals={
                    "conversation_id": conversation_id,
                    # current_user is blank on the pump thread (copy_current_request_context
                    # gives it a fresh, empty g), so carry the identity fs tools need.
                    # Captured as scalars above to avoid a detached-User refresh here.
                    "fs_user_id": fs_user_id,
                    "fs_user_role": fs_user_role,
                },
            ):
                if responses is _HEARTBEAT:
                    yield json.dumps({"heartbeat": True}) + "\n"
                    continue
                if not responses:
                    continue
                last = responses[-1]
                role = last.get("role", "")
                content = last.get("content") or ""
                fn_call = last.get("function_call")

                if role == "assistant":
                    if fn_call:
                        fn_calls_so_far = [
                            r
                            for r in responses
                            if r.get("role") == "assistant" and r.get("function_call")
                        ]
                        if len(fn_calls_so_far) > seen_fn_count:
                            for fc in fn_calls_so_far[seen_fn_count:]:
                                fc_info = fc.get("function_call") or {}
                                if hasattr(fc_info, "name"):
                                    tool_name = fc_info.name or ""
                                    tool_args = fc_info.arguments or ""
                                else:
                                    tool_name = fc_info.get("name", "")
                                    tool_args = fc_info.get("arguments", "")

                                # tl_done claims a task complete — record the id;
                                # the claim is reviewed at stream close, not trusted
                                # outright.
                                if tool_name == "tl_done":
                                    try:
                                        done_id = (json5.loads(tool_args or "{}").get("id") or "").strip()
                                        if done_id:
                                            done_claims[done_id] = ""  # title filled at close
                                    except Exception:
                                        pass
                                    evidence_log.append(f"[claimed done] tl_done({tool_args[:120]})")

                                if tool_name == "mcp_call_tool":
                                    real, params = _unwrap_mcp_call(tool_args)
                                    if real is None:
                                        # Args still streaming in — the real tool name
                                        # isn't present yet. Stop here and re-check this
                                        # same call on the next yield, when args are fuller,
                                        # so the UI shows the real name, not mcp_call_tool.
                                        break
                                    mcp_real_names.append(real)
                                    if real != "mcp_call_tool":
                                        tool_name = real
                                        tool_args = json.dumps(params)

                                _log(f"[TOOL_CALL] {tool_name}({tool_args[:200]})")
                                yield (
                                    json.dumps(
                                        {
                                            "tool_call": {
                                                "tool": tool_name,
                                                "input": tool_args,
                                            }
                                        }
                                    )
                                    + "\n"
                                )
                                seen_fn_count += 1
                    else:
                        if not content.startswith(prev_content):
                            _log(
                                f"[STREAM_RESET] prev={len(prev_content)} new={len(content)} snippet={content[:60]!r}"
                            )
                            new_text = content
                            prev_content = ""
                        else:
                            new_text = content[len(prev_content) :]
                        if new_text:
                            full_response = content
                            yield json.dumps({"chunk": new_text}) + "\n"
                        prev_content = content

                elif role == "function":
                    fn_name = last.get("name", "")
                    if fn_name == "mcp_call_tool" and mcp_real_names:
                        fn_name = mcp_real_names.pop(0)
                    fn_content = content
                    cleaned = _clean_tool_result(
                        fn_content
                        if isinstance(fn_content, str)
                        else json.dumps(fn_content)
                    )
                    status = "error" if '"status": "error"' in cleaned[:100] else "ok"
                    evidence_log.append(f"[tool {fn_name} → {status}] {cleaned[:200]}")
                    _log(
                        f"[TOOL_RESULT] {fn_name} → {status} ({len(cleaned)} chars) | {cleaned[:120]!r}"
                    )
                    yield (
                        json.dumps(
                            {
                                "tool_result": {
                                    "tool": fn_name,
                                    "output": cleaned,
                                }
                            }
                        )
                        + "\n"
                    )
                    try:
                        _ctx = json5.loads(cleaned).get("data", {}).get("_ctx")
                    except Exception:
                        _ctx = None
                    ordered_messages.append(
                        (
                            "tool_result",
                            {
                                "name": fn_name,
                                "tool_call_id": "",
                                "content": _ctx if _ctx else cleaned[:12000],
                            },
                        )
                    )

        except GeneratorExit:
            cancelled = True
            # Client disconnected — can't emit a review prompt. Leave any tl_done
            # claims as the tool set them.
            return
        except Exception as e:
            import traceback

            msg = _llama_error_msg(e)
            _log(f"[STREAM_ERROR] {msg}\n{traceback.format_exc()}")
            yield json.dumps({"error": msg}) + "\n"
            return

        _log(f"[DONE] response={len(full_response)} chars, tool_calls={seen_fn_count}")

        if cancelled:
            return

        # Branch 1: the task-manager reviews each tl_done claim. Agreed ones stay
        # done; disputed ones revert to pending and go to the user (Branch 2) via
        # the task_review event — the frontend yellow-glows them for ratification.
        if done_claims:
            disputed = _review_done_claims(
                conversation_id, list(done_claims), "\n".join(evidence_log[-40:]), db
            )
            if disputed:
                yield json.dumps({"task_review": disputed}) + "\n"

        try:
            user_row = serialize_user_message(user_msg)
            db.add(
                ConversationMessage(
                    conversation_id=conversation_id,
                    role=user_row["role"],
                    content=user_row["content"],
                    tool_calls=user_row["tool_calls"],
                )
            )

            for msg_type, msg_data in ordered_messages:
                if msg_type == "tool_result":
                    result_row = serialize_tool_result(
                        msg_data["name"], msg_data["tool_call_id"], msg_data["content"]
                    )
                    db.add(
                        ConversationMessage(
                            conversation_id=conversation_id,
                            role=result_row["role"],
                            content=result_row["content"],
                            tool_calls=result_row["tool_calls"],
                        )
                    )

            if full_response:
                asst_row = serialize_assistant_message(full_response, tool_calls=[])
                db.add(
                    ConversationMessage(
                        conversation_id=conversation_id,
                        role=asst_row["role"],
                        content=asst_row["content"],
                        tool_calls=asst_row["tool_calls"],
                    )
                )

            conv.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as e:
            logging.getLogger(__name__).error(
                "Failed to persist conversation messages to database: %s",
                e,
                exc_info=True,
            )
            yield (
                json.dumps(
                    {
                        "error": (
                            f"⚠️ Conversation not saved to history — {type(e).__name__} during "
                            f"database write. Your response is shown above but won't appear in history after reload."
                        )
                    }
                )
                + "\n"
            )

        final_messages = list(qwen_messages)
        for msg_type, msg_data in ordered_messages:
            if msg_type == "tool_result":
                final_messages.append(
                    {
                        "role": "function",
                        "name": msg_data["name"],
                        "content": msg_data["content"],
                    }
                )
        if full_response:
            final_messages.append({"role": "assistant", "content": full_response})
        final_pct = round(
            min(
                _estimate_tokens(final_messages, system_prompt, function_list)
                / LLAMA_ARG_CTX_SIZE
                * 100,
                100,
            ),
            1,
        )
        yield json.dumps({"context_pct": final_pct}) + "\n"

        yield (
            json.dumps(
                {
                    "done": True,
                    "full_response": full_response,
                    "conversation_id": conversation_id,
                }
            )
            + "\n"
        )

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@chat_bp.route("/cancel", methods=["POST"])
@login_required
def chat_cancel():
    """Drop the TCP connection to llama-server to abort the current generation.

    ss -K sends a TCP RST to every socket connected to llama-server's port.
    The in-flight httpx stream inside the pump thread gets a ConnectionResetError,
    the pump thread exits, and the Flask generator unblocks — without touching
    the llama-server process itself.
    """
    subprocess.run(
        ["ss", "-K", "dst", f":{LLAMA_PORT}"],
        capture_output=True,
    )
    return jsonify({"status": "cancelled"})


def _group_turns(rows: list) -> list[list]:
    """Split chronological message rows into turns, each starting with a user message.
    Leading non-user rows (shouldn't exist in normal data) are dropped."""
    turns: list[list] = []
    current: list = []
    for row in rows:
        if row.role == "user":
            if current:
                turns.append(current)
            current = [row]
        elif current:
            current.append(row)
    if current:
        turns.append(current)
    return turns


def _turn_transcript(turns: list[list]) -> str:
    lines = []
    for turn in turns:
        for row in turn:
            content = (row.content or "").strip()
            if content:
                lines.append(f"{row.role.upper()}: {content[:3000]}")
    return "\n\n".join(lines)


@chat_bp.route("/summarize", methods=["POST"])
@login_required
def summarize_context():
    """Sliding-window context compression: keep last 7 turns verbatim, summarize turns 8-9.

    More conservative window — preserves context across interruptions and user
    messages that would otherwise get compressed away.
    """
    data = request.get_json(force=True) or {}
    conv_id = data.get("conversation_id")
    if not conv_id:
        return jsonify({"error": "conversation_id required"}), 400

    db = get_db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=current_user.id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    rows = (
        db.query(ConversationMessage)
        .filter_by(conversation_id=conv_id)
        .order_by(ConversationMessage.created_at.asc())
        .all()
    )
    if not rows:
        return jsonify({"context_pct": 0}), 200

    turns = _group_turns(rows)

    if len(turns) <= 7:
        pct = round(
            min(
                _estimate_tokens(
                    [{"role": r.role, "content": r.content or ""} for r in rows]
                )
                / LLAMA_ARG_CTX_SIZE
                * 100,
                100,
            ),
            1,
        )
        return jsonify({"context_pct": pct}), 200

    keep_turns = turns[-7:]
    compress_turns = turns[-9:-7]

    transcript = _turn_transcript(compress_turns)
    try:
        summary = summarize_transcript(transcript)
    except Exception as e:
        return jsonify({"error": f"Summarization failed: {e}"}), 500

    # Snapshot kept rows into plain dicts before the DELETE invalidates ORM state.
    keep_snapshots = [
        [
            {
                "role": r.role,
                "content": r.content or "",
                "tool_calls": r.tool_calls or [],
            }
            for r in turn
        ]
        for turn in keep_turns
    ]

    try:
        db.query(ConversationMessage).filter_by(conversation_id=conv_id).delete()
        db.add(
            ConversationMessage(
                conversation_id=conv_id,
                role="user",
                content=f"[summary]\n{summary}",
                tool_calls=[],
            )
        )
        for turn in keep_snapshots:
            for row in turn:
                db.add(
                    ConversationMessage(
                        conversation_id=conv_id,
                        role=row["role"],
                        content=row["content"],
                        tool_calls=row["tool_calls"],
                    )
                )
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"DB write failed: {e}"}), 500

    kept_messages = [{"role": "user", "content": f"[summary]\n{summary}"}] + [
        {"role": r["role"], "content": r["content"]}
        for turn in keep_snapshots
        for r in turn
    ]
    new_pct = round(
        min(_estimate_tokens(kept_messages) / LLAMA_ARG_CTX_SIZE * 100, 100), 1
    )

    with _dl_lock:
        done = [jid for jid, j in _dl_jobs.items() if j["status"] in ("done", "error")]
        for jid in done:
            del _dl_jobs[jid]

    return jsonify(
        {"context_pct": new_pct, "summary": summary, "dl_jobs_cleared": len(done)}
    )
