import json
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4
import os as _os
from flask import Flask, request, jsonify, Response, stream_with_context, send_file
from flask_login import login_required, current_user
import ollama as ollama_client
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain.agents.structured_output import ResponseFormat
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)
import httpx
from tools import ALL_TOOLS
from prepass import load_tool_index, select_tools
from context import build_history, serialize_user_message, serialize_assistant_message, serialize_tool_result
from auth.conversations import Conversation, ConversationMessage



# ── Auth setup ────────────────────────────────────────────────────────────────
from auth.middleware import login_manager, auth_guard
from auth.routes import auth_bp, init_oauth
from auth.db import init_db, SessionLocal, get_db
import auth.conversations  # register conversation models with Base




# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPT (Qwen-optimized)
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an execution agent with tool access.

RULES:
- If a tool can solve the task, you MUST call it.
- Do NOT explain how to do things.
- Do NOT give instructions.
- Do NOT fabricate data.

TOOL CALL FORMAT:
You MUST respond with JSON when calling tools:

{
  "name": "<tool_name>",
  "params": {...}
}

Example:
{
  "name": "fetch_data",
  "params": {
    "query": "latest weather in New York"
  }
}

If you need to make multiple tool calls, return an array of calls:

[
  {
    "name": "fetch_data",
    "params": {
      "query": "latest weather in New York"
    }
  },
  {
    "name": "analyze_data",
    "params": {
      "data_id": "12345"
    }
  }
]

Do not include any other text or markdown formatting.
"""

# ─────────────────────────────────────────────────────────────
# TOOL CALL PARSER
# ─────────────────────────────────────────────────────────────

def parse_tool_calls(response_content):
    try:
        tool_calls = json.loads(response_content)
        if isinstance(tool_calls, dict) and "name" in tool_calls and "params" in tool_calls:
            return [tool_calls]
        elif isinstance(tool_calls, list) and all(isinstance(call, dict) and "name" in call and "params" in call for call in tool_calls):
            return tool_calls
    except json.JSONDecodeError:
        pass
    return []





app = Flask(__name__)
def _tool_meta(t) -> dict:
    """Extract name, description, and parameter info from a LangChain tool."""
    schema = t.args_schema.schema() if t.args_schema else {}
    props = schema.get("properties", {})
    required = schema.get("required", [])
    params = {}
    for pname, pinfo in props.items():
        params[pname] = {
            "type": pinfo.get("type", "string"),
            "description": pinfo.get("description", ""),
            "required": pname in required,
        }
        if "default" in pinfo:
            params[pname]["default"] = pinfo["default"]
    return {
        "name": t.name,
        "description": t.description.split("\n")[0] if t.description else "",
        "params": params,
    }
    
TOOL_REGISTRY = [_tool_meta(t) for t in ALL_TOOLS]

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
app.before_request(auth_guard)

@app.teardown_appcontext
def shutdown_session(exception=None):
    SessionLocal.remove()

# Create tables on first run (use Alembic migrations in production)
with app.app_context():
    init_db()

# Load compact tool index from tools server at startup
with app.app_context():
    try:
        load_tool_index()
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to load tool index at startup: %s", e)

_FRONTEND_DIST = _os.path.join(_os.path.dirname(__file__), "frontend", "dist")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


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
# AGENT BUILDER
# ─────────────────────────────────────────────────────────────

# Build lookup dict for fetching tools by name
_TOOL_BY_NAME = {t.name: t for t in ALL_TOOLS}

# Per-conversation cache: conversation_id → last tool names used
_last_tool_selection: dict[str, tuple[str, list[str]]] = {}  # conv_id → (model, tool_names)
_last_agent_cache: dict[str, object] = {}


def _build_agent(model_name: str, tool_names: list[str], conversation_id: str | None = None):
    """Build a LangChain agent with only the specified tools bound.

    Caches per conversation_id. If tool_names match the previous turn's
    selection for this conversation, returns the cached agent.

    Args:
        model_name: Ollama model name.
        tool_names: List of tool name strings to bind.
        conversation_id: Optional conversation ID for caching.
    """
    if conversation_id and conversation_id in _last_tool_selection:
        prev_model, prev_tools = _last_tool_selection[conversation_id]
        if prev_model == model_name and sorted(prev_tools) == sorted(tool_names):
            cached = _last_agent_cache.get(conversation_id)
            if cached is not None:
                return cached

    llm = ChatOllama(
        model=model_name,
        temperature=0,
        base_url="http://localhost:11434",
    ).bind(response_format=ResponseFormat.JSON)

    tools = [_TOOL_BY_NAME[name] for name in tool_names if name in _TOOL_BY_NAME]

    agent = create_agent(
        llm,
        tools,
        system_prompt=SYSTEM_PROMPT,
        response_format=ResponseFormat.JSON,
    )

    if conversation_id:
        _last_tool_selection[conversation_id] = (model_name, tool_names)
        _last_agent_cache[conversation_id] = agent

    return agent

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

    # --- Tool pre-pass ---
    fallback_names = _get_user_selected_tools()
    tool_names = select_tools(user_msg, fallback_names)

    agent = _build_agent(model_name, tool_names, conversation_id)

    # --- Assemble messages ---
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content="Respond ONLY with valid JSON when calling tools."),
    ] + history + [
        HumanMessage(content=user_msg),
    ]

    def generate():
        full_response = ""
        # Collect messages in order as (type, data) tuples to preserve
        # correct tool_call → tool_result interleaving for DB persistence
        ordered_messages = []

        # Send conversation_id first so frontend can track it
        yield json.dumps({"conversation_id": conversation_id}) + "\n"

        try:
            for event in agent.stream({"messages": messages}, stream_mode="updates"):
                for node_output in event.values():
                    for msg in node_output.get("messages", []):
                        # Tool calls — LangChain ToolCall is a TypedDict, use dict access
                        if getattr(msg, "tool_calls", None):
                            for call in msg.tool_calls:
                                ordered_messages.append(("tool_call", {
                                    "name": call["name"],
                                    "args": call["args"],
                                    "id": call.get("id", ""),
                                }))
                                yield json.dumps({
                                    "tool_call": {
                                        "tool": call["name"],
                                        "input": str(call["args"])
                                    }
                                }) + "\n"

                        # Tool results
                        elif isinstance(msg, ToolMessage):
                            ordered_messages.append(("tool_result", {
                                "name": msg.name,
                                "tool_call_id": getattr(msg, "tool_call_id", ""),
                                "content": str(msg.content),
                            }))
                            yield json.dumps({
                                "tool_result": {
                                    "tool": msg.name,
                                    "output": str(msg.content)[:500]
                                }
                            }) + "\n"

                        # Normal text
                        elif msg.content:
                            full_response += msg.content
                            yield json.dumps({"chunk": msg.content}) + "\n"

        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        # --- Persist messages to DB (in correct order) ---
        try:
            # Save user message
            user_row = serialize_user_message(user_msg)
            db.add(ConversationMessage(
                conversation_id=conversation_id,
                role=user_row["role"],
                content=user_row["content"],
                tool_calls=user_row["tool_calls"],
            ))

            # Save tool calls and results in the order they occurred
            for msg_type, msg_data in ordered_messages:
                if msg_type == "tool_call":
                    db.add(ConversationMessage(
                        conversation_id=conversation_id,
                        role="assistant",
                        content="",
                        tool_calls=[msg_data],
                    ))
                elif msg_type == "tool_result":
                    result_row = serialize_tool_result(
                        msg_data["name"], msg_data["tool_call_id"], msg_data["content"]
                    )
                    db.add(ConversationMessage(
                        conversation_id=conversation_id,
                        role=result_row["role"],
                        content=result_row["content"],
                        tool_calls=result_row["tool_calls"],
                    ))

            # Save assistant response
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
            # Convert indices to names if user still has old index-based prefs
            if user_tools and isinstance(user_tools[0], int):
                return [ALL_TOOLS[i].name for i in user_tools if i < len(ALL_TOOLS)]
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

    agent = _build_agent(model, [t.name for t in ALL_TOOLS])
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

        messages = history + [HumanMessage(content=user_input)]

        print("Agent: ", end="", flush=True)

        try:
            result = agent.invoke({"messages": messages})
            output_msgs = result.get("messages", [])

            response = ""
            for msg in reversed(output_msgs):
                if isinstance(msg, AIMessage) and msg.content:
                    response = msg.content
                    break

            print(response)

            history.append(HumanMessage(content=user_input))
            history.append(AIMessage(content=response))

        except Exception as e:
            print(f"\n[Error: {e}]")

if __name__ == "__main__":
    main()