import json
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4
import os as _os
from dotenv import load_dotenv

load_dotenv()
from flask import Flask, request, jsonify, Response, stream_with_context, send_file
from flask_login import login_required, current_user
import ollama as ollama_client
from langchain_ollama import ChatOllama
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
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
- Do NOT explain how to do things — just do them.
- Do NOT give instructions — take action.
- Do NOT fabricate data — use your tools.
- Do NOT describe which tools you would use — call them directly.
- When you need information, call the appropriate tool immediately.
- Tool results are shown to you in the conversation. You can read and analyze them directly.
- Do NOT pass placeholder strings like "{result of tool}" to other tools. Use the actual data from the tool result.
- If a tool returns data you need to process, analyze it yourself from the conversation context rather than calling another tool with a placeholder.
- If a tool call returns the same result twice, STOP retrying and work with what you have.
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


# ─────────────────────────────────────────────────────────────
# TOOL FAILURE DETECTION
# ─────────────────────────────────────────────────────────────

def _is_tool_failure(result_str: str) -> bool:
    """Detect if a tool result is an error or empty/useless response."""
    if result_str.startswith("Error:") or result_str.startswith("Unknown tool:"):
        return True
    try:
        parsed = json.loads(result_str)
        if isinstance(parsed, dict):
            # Check for error status
            if parsed.get("status") == "error" or parsed.get("error"):
                return True
            # Check for empty results
            data = parsed.get("data", {})
            if isinstance(data, dict):
                count = data.get("count")
                if count == 0:
                    return True
                for key in ("files", "elements", "matches", "entries", "results"):
                    val = data.get(key)
                    if isinstance(val, list) and len(val) == 0:
                        return True
    except (json.JSONDecodeError, TypeError):
        pass
    return False


# ─────────────────────────────────────────────────────────────
# TOOL CALL PARSER
# ─────────────────────────────────────────────────────────────

def parse_tool_calls(response_content):
    """Parse tool calls from model text output.

    Handles both {name, params} and {name, arguments} formats,
    and strips <tools>...</tools> wrappers from abliterated models.
    """
    text = response_content.strip()
    # Strip <tools>...</tools> wrapper
    import re as _re
    match = _re.search(r"<tools>(.*?)</tools>", text, flags=_re.DOTALL)
    if match:
        text = match.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from mixed text
        match = _re.search(r"[\[{].*[\]}]", text, flags=_re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    def _normalize(call):
        """Normalize a tool call dict to {name, params}."""
        if not isinstance(call, dict) or "name" not in call:
            return None
        params = call.get("params") or call.get("arguments") or {}
        return {"name": call["name"], "params": params}

    if isinstance(parsed, dict):
        norm = _normalize(parsed)
        return [norm] if norm else []
    elif isinstance(parsed, list):
        results = [_normalize(c) for c in parsed if isinstance(c, dict)]
        return [r for r in results if r]
    return []





app = Flask(__name__)
app.secret_key = _os.environ.get("FLASK_SECRET_KEY", "dev-fallback-key-change-in-production")
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

# Per-conversation cache: conversation_id → (model, tool_names, llm)
_llm_cache: dict[str, tuple[str, list[str], object]] = {}

MAX_TOOL_ROUNDS = 30  # safety limit on tool-calling loop


def _get_llm(model_name: str, tool_names: list[str], conversation_id: str | None = None):
    """Get a ChatOllama instance with tools bound for schema awareness.

    Caches per conversation_id to avoid rebuilding when tool selection
    hasn't changed.
    """
    if conversation_id and conversation_id in _llm_cache:
        prev_model, prev_tools, cached_llm = _llm_cache[conversation_id]
        if prev_model == model_name and sorted(prev_tools) == sorted(tool_names):
            return cached_llm

    llm = ChatOllama(
        model=model_name,
        temperature=0,
        base_url="http://localhost:11434",
        timeout=120,  # seconds — prevents hanging if Ollama stalls
    )

    if conversation_id:
        _llm_cache[conversation_id] = (model_name, tool_names, llm)

    return llm

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

    # --- Tool pre-pass ---
    print(f"[PREPASS_START]", flush=True)
    fallback_names = _get_user_selected_tools()
    tool_names = select_tools(user_msg, fallback_names)

    print(f"[CHAT] model={model_name}, prepass_selected={len(tool_names)} tools: {tool_names}, conv={conversation_id}", flush=True)

    llm = _get_llm(model_name, tool_names, conversation_id)

    # --- Build tool schema block for system prompt ---
    tool_schemas = []
    for name in tool_names:
        t = _TOOL_BY_NAME.get(name)
        if t:
            schema = t.args_schema.model_json_schema() if t.args_schema else {}
            props = schema.get("properties", {})
            params_desc = ", ".join(f'{k}: {v.get("type", "str")}' for k, v in props.items())
            desc = (t.description.split("\n")[0] if t.description else "")
            tool_schemas.append(f'- {name}({params_desc}): {desc}')

    tools_block = "\n".join(tool_schemas)

    system_with_tools = f"""{SYSTEM_PROMPT}

AVAILABLE TOOLS:
{tools_block}

To call a tool, respond with ONLY a JSON array like:
[{{"name": "tool_name", "arguments": {{"param": "value"}}}}]

If you do not need to call a tool, respond with plain text."""

    # --- Assemble messages ---
    messages = [
        SystemMessage(content=system_with_tools),
    ] + history + [
        HumanMessage(content=user_msg),
    ]

    def generate():
        nonlocal messages
        full_response = ""
        ordered_messages = []
        prev_call_sig = None  # detect repeated identical tool calls

        yield json.dumps({"conversation_id": conversation_id}) + "\n"

        try:
            for _round in range(MAX_TOOL_ROUNDS):
                print(f"[ROUND {_round}] invoking LLM with {len(messages)} messages", flush=True)

                # Buffer the full streamed response, then decide what to do
                chunks = []
                for chunk in llm.stream(messages):
                    token = chunk.content or ""
                    if token:
                        chunks.append(token)

                content = "".join(chunks)
                print(f"[ROUND {_round}] got {len(content)} chars, starts with: {content[:80]!r}", flush=True)

                # Check for tool calls
                calls = parse_tool_calls(content)

                if not calls:
                    # Final text response — replay buffered tokens for streaming effect
                    for token in chunks:
                        full_response += token
                        yield json.dumps({"chunk": token}) + "\n"
                    break

                # Detect repeated tool calls (stuck in a loop) — compare names only,
                # not params (which may contain varying HTML content)
                call_sig = json.dumps([c["name"] for c in calls], sort_keys=True)
                if call_sig == prev_call_sig:
                    print(f"[ROUND {_round}] LOOP DETECTED — same tool calls as previous round, breaking", flush=True)
                    # Tell the model to stop and respond with what it has
                    messages.append(AIMessage(content=content))
                    messages.append(HumanMessage(
                        content="STOP: You are repeating the same tool calls. The previous attempt returned the same result. Summarize what you know so far and respond to the user."
                    ))
                    # Do one more round for final text
                    final_chunks = []
                    for chunk in llm.stream(messages):
                        token = chunk.content or ""
                        if token:
                            final_chunks.append(token)
                            # Stream immediately — this should be text
                            full_response += token
                            yield json.dumps({"chunk": token}) + "\n"
                    break
                prev_call_sig = call_sig

                # Tool call round — process tools
                messages.append(AIMessage(content=content))
                for call in calls:
                    tool_name = call["name"]
                    tool_params = call["params"]

                    # Stream tool_call event to frontend
                    yield json.dumps({
                        "tool_call": {
                            "tool": tool_name,
                            "input": json.dumps(tool_params),
                        }
                    }) + "\n"

                    # Execute the tool with self-correcting retry
                    tool_obj = _TOOL_BY_NAME.get(tool_name)
                    if not tool_obj:
                        result_str = f"Unknown tool: {tool_name}"
                    else:
                        retry_attempts = []
                        max_retries = 3
                        result_str = None

                        for attempt in range(max_retries):
                            try:
                                result = tool_obj.invoke(tool_params)
                                result_str = str(result)
                            except Exception as tool_err:
                                result_str = f"Error: {tool_err}"

                            # Check if the result is an error or empty
                            is_error = _is_tool_failure(result_str)

                            if not is_error or attempt == max_retries - 1:
                                break

                            # Self-correct: ask the LLM what to fix
                            retry_attempts.append({
                                "params": tool_params,
                                "result": result_str[:500],
                            })

                            if attempt == 0:
                                fix_prompt = (
                                    f"Tool '{tool_name}' was called with {json.dumps(tool_params)} "
                                    f"but returned an error/empty result: {result_str[:500]}\n\n"
                                    f"What caused this error? What would you change about the "
                                    f"parameters to make it succeed? Respond with ONLY a JSON "
                                    f"object of corrected parameters, nothing else."
                                )
                            else:
                                history_str = "\n".join(
                                    f"  Attempt {i+1}: params={json.dumps(a['params'])}, result={a['result']}"
                                    for i, a in enumerate(retry_attempts)
                                )
                                fix_prompt = (
                                    f"Tool '{tool_name}' has failed {len(retry_attempts)} times:\n"
                                    f"{history_str}\n\n"
                                    f"What would you change this time? Respond with ONLY a JSON "
                                    f"object of corrected parameters, nothing else."
                                )

                            print(f"[RETRY] {tool_name} attempt {attempt+1} failed, asking LLM to fix", flush=True)

                            # Ask LLM for corrected params
                            try:
                                fix_resp = llm.invoke([
                                    SystemMessage(content="You are fixing a failed tool call. Respond with ONLY valid JSON parameters."),
                                    HumanMessage(content=fix_prompt),
                                ])
                                fix_text = fix_resp.content.strip()
                                # Extract JSON from response
                                fix_match = re.search(r'\{.*\}', fix_text, flags=re.DOTALL)
                                if fix_match:
                                    new_params = json.loads(fix_match.group())
                                    print(f"[RETRY] LLM suggested: {json.dumps(new_params)}", flush=True)
                                    tool_params = new_params

                                    # Stream the retry to frontend
                                    yield json.dumps({
                                        "tool_call": {
                                            "tool": f"{tool_name} (retry {attempt+2})",
                                            "input": json.dumps(tool_params),
                                        }
                                    }) + "\n"
                            except Exception:
                                break  # can't self-correct, use what we have

                    # Stream tool_result event to frontend
                    yield json.dumps({
                        "tool_result": {
                            "tool": tool_name,
                            "output": result_str[:500],
                        }
                    }) + "\n"

                    ordered_messages.append(("tool_call", {
                        "name": tool_name,
                        "args": tool_params,
                        "id": "",
                    }))
                    ordered_messages.append(("tool_result", {
                        "name": tool_name,
                        "tool_call_id": "",
                        "content": result_str,
                    }))

                    # Clean HTML noise and truncate before feeding back to LLM
                    cleaned = _clean_tool_result(result_str)
                    truncated = cleaned[:12000]
                    if len(cleaned) > 12000:
                        truncated += f"\n... (truncated, {len(cleaned)} chars total)"
                    print(f"[TOOL] {tool_name}: raw={len(result_str)} → cleaned={len(cleaned)} → ctx={len(truncated)}", flush=True)
                    messages.append(HumanMessage(
                        content=f"Tool '{tool_name}' returned:\n{truncated}"
                    ))

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

    llm = _get_llm(model, [t.name for t in ALL_TOOLS])
    history = [SystemMessage(content=SYSTEM_PROMPT)]

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

        history.append(HumanMessage(content=user_input))
        print("Agent: ", end="", flush=True)

        try:
            for _round in range(MAX_TOOL_ROUNDS):
                resp = llm.invoke(history)
                content = resp.content or ""
                calls = parse_tool_calls(content)

                if not calls:
                    print(content)
                    history.append(AIMessage(content=content))
                    break

                history.append(AIMessage(content=content))
                for call in calls:
                    tool_name = call["name"]
                    tool_params = call["params"]
                    print(f"\n  [calling {tool_name}({tool_params})]")
                    tool_obj = _TOOL_BY_NAME.get(tool_name)
                    if tool_obj:
                        try:
                            result = str(tool_obj.invoke(tool_params))
                        except Exception as te:
                            result = f"Error: {te}"
                    else:
                        result = f"Unknown tool: {tool_name}"
                    print(f"  [result: {result[:200]}]")
                    history.append(HumanMessage(
                        content=f"Tool '{tool_name}' returned:\n{result}"
                    ))
                print("Agent: ", end="", flush=True)

        except Exception as e:
            print(f"\n[Error: {e}]")

if __name__ == "__main__":
    main()