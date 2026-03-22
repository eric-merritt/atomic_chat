import json
import re
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

DEFAULT_TOOL_NAMES = {"read", "info", "ls", "tree", "write", "append", "replace", "insert", "delete", "copy", "move", "mkdir", "grep", "find", "definition", "webscrape", "find_all", "find_download_link" }
DEFAULT_TOOL_INDICES = [i for i, t in enumerate(TOOL_REGISTRY) if t["name"] in DEFAULT_TOOL_NAMES]

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

def _build_agent(model_name, selected_tools):
    llm = ChatOllama(
        model=model_name,
        temperature=0,
        base_url="http://localhost:11434",
    ).bind(response_format=ResponseFormat.JSON)

    tools = [t for i, t in enumerate(ALL_TOOLS) if i in selected_tools]

    return create_agent(
        llm,
        tools,
        system_prompt=SYSTEM_PROMPT,
        response_format=ResponseFormat.JSON,
    )

# ─────────────────────────────────────────────────────────────
# STREAMING CHAT
# ─────────────────────────────────────────────────────────────

@app.route("/api/chat/stream", methods=["POST"])
@login_required
def chat_stream():
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()

    if not user_msg:
        return jsonify({"error": "message required"}), 400

    prefs = current_user.preferences or {}
    model_name = prefs.get("model")
    selected_tools = prefs.get("selected_tools", [])

    if not model_name:
        return jsonify({"error": "No model selected"}), 400

    agent = _build_agent(model_name, selected_tools)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content="Respond ONLY with valid JSON when calling tools."),
        HumanMessage(content=user_msg),
    ]

    def generate():
        full_response = ""

        try:
            for event in agent.stream({"messages": messages}, stream_mode="updates"):
                for node_output in event.values():
                    for msg in node_output.get("messages", []):
                        # Tool calls
                        if getattr(msg, "tool_calls", None):
                            for call in msg.tool_calls:
                                yield json.dumps({
                                    "tool_call": {
                                        "tool": call.name,
                                        "input": str(call.args)
                                    }
                                }) + "\n"

                        # Tool results
                        elif isinstance(msg, ToolMessage):
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

        yield json.dumps({
            "done": True,
            "full_response": full_response
        }) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _get_user_selected_tools():
    """Get selected tool indices for the current user, falling back to defaults."""
    if hasattr(current_user, 'preferences') and current_user.preferences:
        user_tools = current_user.preferences.get("selected_tools")
        if user_tools is not None:
            return user_tools
    return list(DEFAULT_TOOL_INDICES)


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

    agent = _build_agent(model, list(range(len(ALL_TOOLS))))
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