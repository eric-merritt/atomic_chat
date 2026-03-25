import json
import logging
import threading
from datetime import datetime, timezone
import os as _os
from dotenv import load_dotenv

load_dotenv()
from flask import Flask, request, jsonify, Response, stream_with_context, send_file
from flask_login import login_required, current_user
import ollama as ollama_client
import json5
from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool, TOOL_REGISTRY as QW_TOOL_REGISTRY
import tools  # triggers @register_tool side-effects for all tool modules
from config import qwen_llm_cfg
from task_extractor import extract_tasks
from tool_curator import curate_tools
from workflow_groups import WORKFLOW_GROUPS, tools_for_groups
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

SYSTEM_PROMPT = """You are an execution agent with tool access.

RULES:
- If tools can solve the task, call them. Chain multiple tools in series when needed — carry data forward from each result.
- Follow instructions explicitly. Return data in the exact format requested.
- When stuck on tool flow, ask the user — show your plan up to the sticking point.
- Never explain, instruct, describe tools, or summarize unless asked. Act.
- Never fabricate data. Never use placeholder strings in tool arguments — use actual values from the user message or prior tool results.
- Copy strings from the user message EXACTLY as written into tool arguments. Preserve hyphens, dots, spaces, and special characters. If the user writes "img.lazy-loaded", the tool argument must be exactly "img.lazy-loaded".
- Tool results appear in conversation. Read and analyze them directly.
- If a tool returns the same result twice, stop retrying and work with what you have.
- When a [TASK LIST] is present and you complete a task, call mark_task_done with the task number to mark it done. Do this immediately after completing each task, before moving to the next.
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


# Snapshot qwen-agent built-in tool names before our registrations
_BUILTIN_TOOL_NAMES = set(QW_TOOL_REGISTRY.keys())

TOOL_REGISTRY: list[dict] = []  # populated below after internal tools are defined

DEFAULT_TOOL_NAMES = ["read", "info", "ls", "tree", "write", "append", "replace", "insert",
                      "delete", "copy", "move", "mkdir", "grep", "find", "definition",
                      "webscrape", "find_all", "find_download_link"]

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

@register_tool('mark_task_done')
class MarkTaskDoneTool(BaseTool):
    description = 'Mark a task as done by its 1-based number from the [TASK LIST].'
    parameters = {
        'type': 'object',
        'properties': {
            'task_number': {'type': 'integer', 'description': '1-based task number from [TASK LIST].'},
            'conversation_id': {'type': 'string', 'description': 'Active conversation ID.'},
        },
        'required': ['task_number', 'conversation_id'],
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
            'conversation_id': {'type': 'string', 'description': 'Active conversation ID.'},
        },
        'required': ['task_number', 'conversation_id'],
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
        conversation_id = p.get('conversation_id', '')
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

    # --- Task Extractor + Tool Curator pipeline ---
    user_tool_names = _get_user_selected_tools()
    has_new_tasks = extract_tasks(user_msg, conversation_id, db)
    curation = curate_tools(conversation_id, user_tool_names, has_new_tasks, db)

    print(f"[CURATION] new_tasks={has_new_tasks}, action={curation.action}, groups={curation.groups}", flush=True)

    # tool_names will be finalized inside generate() after recommendation flow
    _initial_tool_names = user_tool_names

    # --- Append conversation tasks to user message ---
    conv_tasks = (
        db.query(ConversationTask)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationTask.created_at.asc())
        .all()
    )
    augmented_msg = user_msg
    if conv_tasks:
        tool_hints = {m.task_title: m.tool for m in curation.task_plan} if curation.task_plan else {}
        task_lines = []
        for i, ct in enumerate(conv_tasks, 1):
            hint = tool_hints.get(ct.title, "")
            suffix = f" → use {hint}" if hint and hint != "mcp" else ""
            task_lines.append(f"  {i}. [{ct.status}] {ct.title}{suffix}")
        augmented_msg += "\n\n[TASK LIST]\n" + "\n".join(task_lines)
        if any(m.tool == "mcp" for m in curation.task_plan):
            augmented_msg += "\n\nNote: Tasks without a tool hint may require external MCP tools. Use connect_to_mcp if needed."

    def generate():
        full_response = ""
        ordered_messages = []

        yield json.dumps({"conversation_id": conversation_id}) + "\n"

        # --- Recommendation flow ---
        accepted_groups: list[str] = []
        if curation.action == "recommend":
            yield json.dumps({"recommendation": {
                "groups": curation.groups,
                "reason": curation.reason,
            }}) + "\n"

            event = threading.Event()
            _recommendation_events[conversation_id] = event
            try:
                event.wait(timeout=120)
                accepted_groups = _recommendation_responses.pop(conversation_id, [])
            finally:
                _recommendation_events.pop(conversation_id, None)

            print(f"[CURATION] User accepted groups: {accepted_groups}", flush=True)

        # Resolve final tool set
        final_tool_names = list(_initial_tool_names)
        if accepted_groups:
            extra_tools = tools_for_groups(accepted_groups)
            final_tool_names = list(set(final_tool_names + extra_tools))
            print(f"[CHAT] final tool set: {len(final_tool_names)} tools", flush=True)

        # Build function_list for qwen-agent — only tools in TOOL_REGISTRY
        function_list = [n for n in final_tool_names if n in QW_TOOL_REGISTRY]
        function_list += ['mark_task_done', 'unmark_task_done']

        assistant = Assistant(
            llm=qwen_llm_cfg(model_name),
            function_list=function_list,
            system_message=SYSTEM_PROMPT,
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
                return [n for n in user_tools if n in QW_TOOL_REGISTRY]
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

    function_list = list(QW_TOOL_REGISTRY.keys())
    assistant = Assistant(
        llm=qwen_llm_cfg(model),
        function_list=function_list,
        system_message=SYSTEM_PROMPT,
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