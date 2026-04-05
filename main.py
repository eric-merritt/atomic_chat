import json
import logging
import re
import threading
from datetime import datetime, timezone
import os as _os
from dotenv import load_dotenv

load_dotenv()
from flask import Flask, request, jsonify, Response, stream_with_context, send_file, g
from flask_login import login_required, current_user
import ollama as ollama_client
import json5
from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool, TOOL_REGISTRY as QW_TOOL_REGISTRY
_BUILTIN_TOOL_NAMES = set(QW_TOOL_REGISTRY.keys())
import tools  # triggers @register_tool side-effects for all tool modules
from config import qwen_llm_cfg
from change_hats import analyze_message
from workflow_groups import WORKFLOW_GROUPS, tools_for_groups, group_for_tool
from context import build_history, serialize_user_message, serialize_assistant_message, serialize_tool_result
from auth.conversations import Conversation, ConversationMessage



# ── Auth setup ────────────────────────────────────────────────────────────────
from auth.middleware import login_manager, auth_guard
from auth.routes import auth_bp, init_oauth
from auth.db import init_db, SessionLocal, get_db
import auth.conversations  # register conversation models with Base
from auth.conversation_tasks import ConversationTask




# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPT (Qwen-optimized)
# ─────────────────────────────────────────────────────────────

_SYSTEM_BASE = """You are a conversational agent with tool calling capabilities. If a message requires tools you must call them. If it does not, be conversational.

TOOL REFERENCE:
{tool_ref}

Before calling any tool, call get_params(tool_name) first to learn its required and optional parameters. This is mandatory — never guess parameters.

RULES:
- ONLY call tools listed in TOOL REFERENCE above. NEVER invent tool names.
- ALWAYS begin responding immediately to be polite, even if just to say "Absolutely, let me think about the best way to do this." This ensures that even if you have to call tools, the user feels like they're conversing with a friend.
- NEVER call a tool without first finding its required parameters. Once you find which parameters are needed, infer them from the user message. If the parameters are not included in the user message, ask the user for them specifically.
- The user message is your PRIMARY source of data you'll need to complete tool calls. Read it carefully for: details, parameters, URLs, names, and other constraints.
- A [TASK LIST] may appear below the message. While this can inform you of the current state of the tasks, it should NOT be used to infer parameters, URLs, etc. Use ONLY the user message.
- If it is NECESSARY to call tools, call them. Chain multiple tools in series when needed — the output of one tool call SHOULD provide parameters needed for the next tool call. If it does NOT, the Toolchain is broken and you must re-think it. Use error messages as hints on how to move forward without bothering the user.
- Follow instructions explicitly. Return data in the exact format requested.
- When stuck on tool flow, ask the user — show your plan up to the sticking point.
- ACT FIRST, explain later. Do NOT explain to the user how you're going to perform a task.
- The ONLY time it is acceptable to respond with a tool's content, is when a user asks you about a specific tool or group of tools. These should be formatted in human readable format, not JSON.
- Every tool call MUST include arguments.
- NEVER call a tool with empty or missing arguments — always pass the required parameters.
- NEVER fabricate data — use actual values from the user message or prior tool results.
- NEVER use placeholder strings in tool arguments — use actual values from the user message or prior tool results. "example.com", "path/to/file", "your_query_here" are ALL placeholders. Use REAL data.
- Copy strings from the user message EXACTLY as written into tool arguments. Preserve hyphens, dots, spaces, and special characters. If the user writes "img.lazy-loaded", the tool argument must be exactly "img.lazy-loaded".
- Tool results appear in conversation. Read and analyze them directly.
- If a tool returns the same result twice, stop retrying and work with what you have.
"""

# ─────────────────────────────────────────────────────────────
# HTML STRIPPING (for cleaner LLM context)
# ─────────────────────────────────────────────────────────────

def _strip_html_noise(html: str) -> str:
    """Strip non-structural noise from HTML for LLM consumption.

    Removes: <head>, <script>, <style>, <svg>, <noscript>, comments,
    inline style/onclick attrs, data- attrs. Keeps structural <body> content.
    """
    # Remove entire <head>...</head> (meta, CSS, etc. — useless for element finding)
    cleaned = re.sub(r'<head\b[^>]*>[\s\S]*?</head>', '', html, flags=re.IGNORECASE)
    # Remove script, style, svg, noscript blocks
    cleaned = re.sub(r'<script\b[^>]*>[\s\S]*?</script>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<style\b[^>]*>[\s\S]*?</style>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<svg\b[^>]*>[\s\S]*?</svg>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<noscript\b[^>]*>[\s\S]*?</noscript>', '', cleaned, flags=re.IGNORECASE)
    # Remove HTML comments
    cleaned = re.sub(r'<!--[\s\S]*?-->', '', cleaned)
    # Remove inline style, onclick, onload, data- attributes
    cleaned = re.sub(r'\s+style="[^"]*"', '', cleaned)
    cleaned = re.sub(r"\s+style='[^']*'", '', cleaned)
    cleaned = re.sub(r'\s+on\w+="[^"]*"', '', cleaned)
    cleaned = re.sub(r'\s+data-\w+="[^"]*"', '', cleaned)
    # Collapse whitespace
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n ', '\n', cleaned)
    return cleaned.strip()


def _clean_tool_result(result_str: str) -> str:
    """If a tool result contains HTML, strip noise before feeding to LLM."""
    try:
        parsed = json.loads(result_str)
        if isinstance(parsed, dict):
            data = parsed.get("data", {})
            if isinstance(data, dict) and "html" in data:
                data["html"] = _strip_html_noise(data["html"])
                return json.dumps(parsed)
    except (json.JSONDecodeError, TypeError):
        pass
    # If the raw string looks like HTML, strip it
    if '<html' in result_str[:500].lower() or '<!doctype' in result_str[:500].lower():
        return _strip_html_noise(result_str)
    return result_str





app = Flask(__name__)
app.secret_key = _os.environ.get("FLASK_SECRET_KEY", "dev-fallback-key-change-in-production")


def _tool_meta(cls) -> dict:
    """Extract name, description, and parameter info from a qwen-agent tool class."""
    schema = getattr(cls, 'parameters', {}) or {}
    props = schema.get('properties', {})
    required = schema.get('required', [])
    params = {}
    for pname, pinfo in props.items():
        params[pname] = {
            'type': pinfo.get('type', 'string'),
            'description': pinfo.get('description', ''),
            'required': pname in required,
        }
        if 'default' in pinfo:
            params[pname]['default'] = pinfo['default']
    name = cls.name if hasattr(cls, 'name') else ''
    desc = (cls.description or '').split('\n')[0]
    return {'name': name, 'description': desc, 'params': params}


TOOL_REGISTRY: list[dict] = []  # populated below after internal tools are defined

DEFAULT_TOOL_NAMES = ["fs_read", "fs_info", "fs_ls", "fs_tree", "fs_write", "fs_append",
                      "fs_replace", "fs_insert_at_line", "fs_delete", "fs_copy", "fs_move",
                      "fs_create_directory", "cs_grep", "cs_find", "cs_def",
                      "www_scrape", "www_find_all", "www_find_dl"]

login_manager.init_app(app)
init_oauth(app)
app.register_blueprint(auth_bp)
from routes.conversations import conv_bp
app.register_blueprint(conv_bp)
from routes.preferences import prefs_bp
app.register_blueprint(prefs_bp)
from routes.accounting import acct_bp
app.register_blueprint(acct_bp)
from routes.tools import tools_bp
app.register_blueprint(tools_bp)
app.before_request(auth_guard)

@app.teardown_appcontext
def shutdown_session(exception=None):
    SessionLocal.remove()

# Create tables on first run (use Alembic migrations in production)
with app.app_context():
    init_db()

# Per-conversation recommendation responses (for accept/dismiss flow)
_recommendation_events: dict[str, threading.Event] = {}
_recommendation_responses: dict[str, list[str]] = {}

_FRONTEND_DIST = _os.path.join(_os.path.dirname(__file__), "frontend", "dist")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/chat/recommend", methods=["POST"])
@login_required
def handle_recommendation():
    """Handle user's accept/dismiss of a tool recommendation."""
    data = request.get_json(force=True)
    conversation_id = data.get("conversation_id")
    accepted_groups = data.get("accepted_groups", [])

    if not conversation_id:
        return jsonify({"error": "conversation_id required"}), 400

    _recommendation_responses[conversation_id] = accepted_groups
    event = _recommendation_events.get(conversation_id)
    if event:
        event.set()

    return jsonify({"status": "ok"})


@app.route("/api/workflows", methods=["GET"])
@login_required
def list_workflows():
    """List available workflow groups with full tool metadata."""
    meta_by_name = {t["name"]: t for t in TOOL_REGISTRY}
    groups = []
    for name, group in WORKFLOW_GROUPS.items():
        tools = []
        for tool_name in group.tools:
            t = meta_by_name.get(tool_name)
            if t:
                tools.append({
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "params": t.get("params", {}),
                })
            else:
                tools.append({
                    "name": tool_name,
                    "description": "",
                    "params": {},
                })
        groups.append({
            "name": name,
            "tooltip": group.tooltip,
            "tools": tools,
        })
    return jsonify({"groups": groups})


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """Serve React SPA from frontend/dist/. """
    file_path = _os.path.join(_FRONTEND_DIST, path)
    if path and _os.path.isfile(file_path):
        return send_file(file_path)
    index = _os.path.join(_FRONTEND_DIST, "index.html")
    if _os.path.isfile(index):
        return send_file(index)
    return "Frontend not built. Run: cd frontend && npm run build", 404

# ─────────────────────────────────────────────────────────────
# INTERNAL TOOLS (mark_task_done / unmark_task_done)
# Registered as qwen-agent tools so Assistant handles them natively.
# ─────────────────────────────────────────────────────────────

@register_tool('get_params')
class GetParamsTool(BaseTool):
    description = 'Look up a tool\'s parameters before calling it. Returns param names, types, descriptions, and which are required.'
    parameters = {
        'type': 'object',
        'properties': {
            'tool_name': {'type': 'string', 'description': 'Name of the tool to look up.'},
        },
        'required': ['tool_name'],
    }

    def call(self, params: str, **kwargs) -> dict:
        from tools._output import tool_result
        p = json5.loads(params)
        name = p.get('tool_name', '')
        cls = QW_TOOL_REGISTRY.get(name)
        if not cls:
            return tool_result(error=f"Unknown tool '{name}'")
        schema = getattr(cls, 'parameters', {})
        props = schema.get('properties', {})
        required = set(schema.get('required', []))
        param_list = []
        for pname, pdef in props.items():
            param_list.append({
                "name": pname,
                "type": pdef.get("type", "string"),
                "required": pname in required,
                "description": pdef.get("description", ""),
            })
        return tool_result(data={
            "tool": name,
            "description": getattr(cls, 'description', ''),
            "params": param_list,
        })


@register_tool('list_tools')
class ListToolsTool(BaseTool):
    description = 'List all available tool names grouped by workflow category. Call this when the user asks what tools you have.'
    parameters = {
        'type': 'object',
        'properties': {},
        'required': [],
    }

    def call(self, params: str, **kwargs) -> dict:
        from tools._output import tool_result
        groups = {}
        for name, group in WORKFLOW_GROUPS.items():
            groups[name] = {
                "tooltip": group.tooltip,
                "tools": group.tools,
            }
        # Add internal tools
        groups["Internal"] = {
            "tooltip": "Task management",
            "tools": ["mark_task_done", "unmark_task_done", "list_tools"],
        }
        return tool_result(data=groups)


@register_tool('mark_task_done')
class MarkTaskDoneTool(BaseTool):
    description = 'Mark a task as done by its 1-based number from the [TASK LIST].'
    parameters = {
        'type': 'object',
        'properties': {
            'task_number': {'type': 'integer', 'description': '1-based task number from [TASK LIST].'},
        },
        'required': ['task_number'],
    }

    def call(self, params: str, **kwargs) -> dict:
        return _update_task_status(params, 'done')


@register_tool('unmark_task_done')
class UnmarkTaskDoneTool(BaseTool):
    description = 'Revert a done task back to pending by its 1-based number from the [TASK LIST].'
    parameters = {
        'type': 'object',
        'properties': {
            'task_number': {'type': 'integer', 'description': '1-based task number from [TASK LIST].'},
        },
        'required': ['task_number'],
    }

    def call(self, params: str, **kwargs) -> dict:
        return _update_task_status(params, 'pending')


def _update_task_status(params_str: str, new_status: str) -> dict:
    """Shared implementation for mark/unmark task tools."""
    from auth.db import SessionLocal
    from auth.conversation_tasks import ConversationTask
    from tools._output import tool_result
    try:
        p = json5.loads(params_str)
        task_number = int(p.get('task_number', 0))
        conversation_id = g.get('conversation_id', '')
        db = SessionLocal()
        try:
            ordered = (
                db.query(ConversationTask)
                .filter_by(conversation_id=conversation_id)
                .order_by(ConversationTask.created_at.asc())
                .all()
            )
            if 1 <= task_number <= len(ordered):
                task = ordered[task_number - 1]
                task.status = new_status
                db.commit()
                verb = 'marked done' if new_status == 'done' else 'reverted to pending'
                return tool_result(data=f'Task {task_number} {verb}: {task.title}')
            return tool_result(error=f'Invalid task number {task_number}. Valid range: 1-{len(ordered)}')
        finally:
            db.close()
    except Exception as e:
        from tools._output import tool_result as tr
        return tr(error=str(e))


# Populate TOOL_REGISTRY now that all tools (including internal) are registered
TOOL_REGISTRY = [_tool_meta(cls) for cls in QW_TOOL_REGISTRY.values()
                 if cls.name not in _BUILTIN_TOOL_NAMES]


# ─────────────────────────────────────────────────────────────
# STREAMING CHAT
# ─────────────────────────────────────────────────────────────

@app.route("/api/chat/stream", methods=["POST"])
@login_required
def chat_stream():
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    conversation_id = data.get("conversation_id")

    if not user_msg:
        return jsonify({"error": "message required"}), 400

    prefs = current_user.preferences or {}
    model_name = prefs.get("model")

    if not model_name:
        return jsonify({"error": "No model selected"}), 400

    print(f"[CHAT_START] user_msg={user_msg[:50]!r}, conv_id={conversation_id}, model={model_name}", flush=True)

    db = get_db()

    # --- Conversation management ---
    if conversation_id:
        conv = db.query(Conversation).filter_by(
            id=conversation_id, user_id=current_user.id
        ).first()
        if not conv:
            return jsonify({"error": "Conversation not found"}), 404
    else:
        conv = Conversation(
            user_id=current_user.id,
            title=user_msg[:60],
            model=model_name,
        )
        db.add(conv)
        db.commit()
        conversation_id = conv.id

    g.conversation_id = conversation_id

    # --- Load conversation history ---
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

    # --- Change Hats: Gate + Plan pipeline ---
    user_tool_names = _get_user_selected_tools()
    analysis = analyze_message(user_msg, conversation_id, user_tool_names, db)

    print(f"[HATS] classification={analysis['classification']}, tasks={len(analysis['task_list'])}", flush=True)

    # Write new tasks from plan to DB
    if analysis["task_list"]:
        existing_titles = {
            t.title.lower()
            for t in db.query(ConversationTask).filter_by(conversation_id=conversation_id).all()
        }
        for task in analysis["task_list"]:
            title = task.get("title", "")
            if title and title.lower() not in existing_titles:
                db.add(ConversationTask(
                    conversation_id=conversation_id,
                    title=title,
                ))
                existing_titles.add(title.lower())
        db.commit()

    # --- Append conversation tasks to user message ---
    conv_tasks = (
        db.query(ConversationTask)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationTask.created_at.asc())
        .all()
    )
    def generate():
        full_response = ""
        ordered_messages = []

        yield json.dumps({"conversation_id": conversation_id}) + "\n"

        # --- Determine tool set based on classification ---
        classification = analysis["classification"]

        # list_tools + internal tools are always available
        _ALWAYS_TOOLS = {"get_params", "list_tools", "mark_task_done", "unmark_task_done", "mcp_connect"}

        if classification == "conversational":
            # Conversational — only list_tools so the model can answer "what tools do you have?"
            function_list = [n for n in _ALWAYS_TOOLS if n in QW_TOOL_REGISTRY]
            print("[CHAT] conversational mode — list_tools only", flush=True)
        else:
            # tool_required or mixed — curator determines which groups to load
            # Determine which groups are needed from the plan
            needed_tools = set()
            for task in analysis["task_list"]:
                for subtask in task.get("subtasks", []):
                    action = subtask.get("action", "")
                    if action not in ("respond", "mark_task_done"):
                        needed_tools.add(action)

            # Map needed tools to their groups
            needed_groups = set()
            for tool_name in needed_tools:
                g = group_for_tool(tool_name)
                if g:
                    needed_groups.add(g)

            # Split into groups the user already has vs groups that need recommendation
            user_set = set(user_tool_names)
            approved_groups = []
            missing_groups = []
            for gname in needed_groups:
                group_tools = set(WORKFLOW_GROUPS[gname].tools)
                if group_tools & user_set:
                    # User already has tools from this group — auto-approve
                    approved_groups.append(gname)
                else:
                    missing_groups.append(gname)

            # Recommend missing groups to user
            if missing_groups:
                missing_tool_names = {t for t in needed_tools if group_for_tool(t) in missing_groups}
                yield json.dumps({"recommendation": {
                    "groups": missing_groups,
                    "reason": f"Tasks need: {', '.join(missing_tool_names)}",
                }}) + "\n"

                event = threading.Event()
                _recommendation_events[conversation_id] = event
                try:
                    event.wait(timeout=120)
                    accepted = _recommendation_responses.pop(conversation_id, [])
                finally:
                    _recommendation_events.pop(conversation_id, None)
                approved_groups.extend(accepted)
                print(f"[HATS] User accepted groups: {accepted}", flush=True)

            # Build function_list from approved groups
            if approved_groups:
                curator_tools = set(tools_for_groups(approved_groups))
                function_list = [n for n in curator_tools if n in QW_TOOL_REGISTRY and n not in _BUILTIN_TOOL_NAMES]
                print(f"[CHAT] tool mode — {len(function_list)} tools from groups {approved_groups}", flush=True)
            else:
                # Planner couldn't map to groups — fall back to all user-selected tools
                function_list = [n for n in user_tool_names if n in QW_TOOL_REGISTRY and n not in _BUILTIN_TOOL_NAMES]
                print(f"[CHAT] tool mode (fallback) — {len(function_list)} user-selected tools", flush=True)
            # Always include internal tools
            for t in _ALWAYS_TOOLS:
                if t in QW_TOOL_REGISTRY and t not in function_list:
                    function_list.append(t)

        # Build system prompt with tool reference
        from workflow_groups import TOOL_REF
        tool_ref_lines = [f"  {n} — {TOOL_REF[n]}" for n in function_list if n in TOOL_REF]
        tool_ref_text = "\n".join(tool_ref_lines) if tool_ref_lines else "(none)"
        system_prompt = _SYSTEM_BASE.format(tool_ref=tool_ref_text)

        # Build augmented message: task list only (tools are in system prompt)
        augmented_msg = user_msg
        if conv_tasks:
            task_lines = [f"  {i}. [{ct.status}] {ct.title}" for i, ct in enumerate(conv_tasks, 1)]
            augmented_msg += "\n\n[TASK LIST]\n" + "\n".join(task_lines)

        assistant = Assistant(
            llm=qwen_llm_cfg(model_name),
            function_list=function_list,
            system_message=system_prompt,
        )

        qwen_messages = history + [{"role": "user", "content": augmented_msg}]

        try:
            prev_content = ""
            seen_fn_count = 0

            for responses in assistant.run(messages=qwen_messages):
                if not responses:
                    continue
                last = responses[-1]
                role = last.get("role", "")
                content = last.get("content") or ""
                fn_call = last.get("function_call")

                if role == "assistant":
                    if fn_call:
                        # Tool is being invoked — emit tool_call event once per new call
                        fn_calls_so_far = [
                            r for r in responses
                            if r.get("role") == "assistant" and r.get("function_call")
                        ]
                        if len(fn_calls_so_far) > seen_fn_count:
                            for fc in fn_calls_so_far[seen_fn_count:]:
                                fc_info = fc.get("function_call", {})
                                yield json.dumps({
                                    "tool_call": {
                                        "tool": fc_info.get("name", ""),
                                        "input": fc_info.get("arguments", ""),
                                    }
                                }) + "\n"
                            seen_fn_count = len(fn_calls_so_far)
                    else:
                        # Streaming text — emit new tokens only
                        new_text = content[len(prev_content):]
                        if new_text:
                            full_response = content
                            yield json.dumps({"chunk": new_text}) + "\n"
                        prev_content = content

                elif role == "function":
                    fn_name = last.get("name", "")
                    fn_content = content
                    # Clean HTML noise before context is stored
                    cleaned = _clean_tool_result(
                        fn_content if isinstance(fn_content, str) else json.dumps(fn_content)
                    )
                    yield json.dumps({
                        "tool_result": {
                            "tool": fn_name,
                            "output": cleaned[:500],
                        }
                    }) + "\n"
                    ordered_messages.append(("tool_result", {
                        "name": fn_name,
                        "tool_call_id": "",
                        "content": cleaned[:12000],
                    }))

        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        # --- Persist messages to DB (in correct order) ---
        try:
            user_row = serialize_user_message(user_msg)
            db.add(ConversationMessage(
                conversation_id=conversation_id,
                role=user_row["role"],
                content=user_row["content"],
                tool_calls=user_row["tool_calls"],
            ))

            for msg_type, msg_data in ordered_messages:
                if msg_type == "tool_result":
                    result_row = serialize_tool_result(
                        msg_data["name"], msg_data["tool_call_id"], msg_data["content"]
                    )
                    db.add(ConversationMessage(
                        conversation_id=conversation_id,
                        role=result_row["role"],
                        content=result_row["content"],
                        tool_calls=result_row["tool_calls"],
                    ))

            if full_response:
                asst_row = serialize_assistant_message(full_response, tool_calls=[])
                db.add(ConversationMessage(
                    conversation_id=conversation_id,
                    role=asst_row["role"],
                    content=asst_row["content"],
                    tool_calls=asst_row["tool_calls"],
                ))

            conv.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as e:
            logging.getLogger(__name__).error("Failed to persist messages: %s", e)

        yield json.dumps({
            "done": True,
            "full_response": full_response,
            "conversation_id": conversation_id,
        }) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _get_user_selected_tools() -> list[str]:
    """Get selected tool names for the current user, falling back to defaults."""
    if hasattr(current_user, 'preferences') and current_user.preferences:
        user_tools = current_user.preferences.get("selected_tools")
        if user_tools is not None:
            # Filter out any stale names not in the registry
            if user_tools and isinstance(user_tools[0], str):
                valid = [n for n in user_tools if n in QW_TOOL_REGISTRY]
                if valid:
                    return valid
            elif user_tools:
                return user_tools
    return list(DEFAULT_TOOL_NAMES)


# ── Models ───────────────────────────────────────────────────────────────────

@app.route("/api/models", methods=["GET"])
@login_required
def list_models():
    """List locally available Ollama models."""
    try:
        models = ollama_client.list()
        names = [m.model for m in models.models]
        prefs = current_user.preferences or {}
        current = prefs.get("model")
        return jsonify({"models": names, "current": current})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/models", methods=["POST"])
@login_required
def select_model():
    """Select an Ollama model. Body: {"model": "name"}"""
    data = request.get_json(force=True)
    model = data.get("model")
    if not model:
        return jsonify({"error": "model required"}), 400
    db = get_db()
    prefs = dict(current_user.preferences or {})
    prefs["model"] = model
    current_user.preferences = prefs
    db.commit()
    return jsonify({"model": model})



# ─────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────

def main():
    import sys

    if "--serve" in sys.argv:
        port = 5000
        for arg in sys.argv:
            if arg.startswith("--port="):
                port = int(arg.split("=")[1])

        print(f"Starting server on http://localhost:{port}")
        app.run(host="0.0.0.0", port=port, debug=True)
        return

    print("=== Agentic Chat (Qwen Tool-Optimized) ===")

    while True:
        print("\n1. Chat")
        print("2. Start API server")
        print("q. Quit")
        app.run(host="0.0.0.0", port=5000, debug=True)

# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def cli_model_picker():
    try:
        models = ollama_client.list()
        names = [m.model for m in models.models]
    except Exception as e:
        print(f"Error listing models: {e}")
        return None

    print("\nAvailable models:")
    for i, name in enumerate(names):
        print(f"{i:>2}. {name}")

    choice = input("\nSelect model #: ").strip()
    if choice.isdigit() and 0 <= int(choice) < len(names):
        return names[int(choice)]

    return None


def cli_chat():
    model = cli_model_picker()
    if not model:
        print("No model selected.")
        return

    print(f"\nChatting with: {model}")
    print("Type 'quit' to exit\n")

    function_list = [n for n in QW_TOOL_REGISTRY.keys() if n not in _BUILTIN_TOOL_NAMES]
    from workflow_groups import TOOL_REF
    tool_ref_lines = [f"  {n} — {TOOL_REF[n]}" for n in function_list if n in TOOL_REF]
    system_prompt = _SYSTEM_BASE.format(tool_ref="\n".join(tool_ref_lines) or "(none)")
    assistant = Assistant(
        llm=qwen_llm_cfg(model),
        function_list=function_list,
        system_message=system_prompt,
    )
    history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break

        history.append({"role": "user", "content": user_input})
        print("Agent: ", end="", flush=True)

        try:
            responses = []
            for responses in assistant.run(messages=history):
                pass
            if responses:
                last = responses[-1]
                if last.get("role") == "assistant" and last.get("content"):
                    print(last["content"])
                    history.append({"role": "assistant", "content": last["content"]})
                elif last.get("role") == "function":
                    print(f"\n  [tool result: {str(last.get('content', ''))[:200]}]")
        except Exception as e:
            print(f"\n[Error: {e}]")

if __name__ == "__main__":
    main()