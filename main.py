import json
import logging
from datetime import datetime, timezone
import os as _os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context, send_file, g
from flask_login import login_required, current_user
import ollama as ollama_client
import json5
from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool, TOOL_REGISTRY as QW_TOOL_REGISTRY

_BUILTIN_TOOL_NAMES = set(QW_TOOL_REGISTRY.keys())

import tools  # triggers @register_tool side-effects for all tool modules
from tools.web import _strip_html_noise
from config import qwen_llm_cfg
from pipeline.workflow_groups import WORKFLOW_GROUPS, TOOL_REF
from context import build_history, serialize_user_message, serialize_assistant_message, serialize_tool_result
from auth.conversations import Conversation, ConversationMessage
from auth.middleware import login_manager, auth_guard
from auth.routes import auth_bp, init_oauth
from auth.db import init_db, SessionLocal, get_db
from auth.conversation_tasks import ConversationTask

load_dotenv()



# ── Auth setup ────────────────────────────────────────────────



# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPT (Qwen-optimized)
# ─────────────────────────────────────────────────────────────
tool_ref = tools.ALL_TOOLS

_SYSTEM_BASE = """You are a helpful, friendly assistant. You're great at conversation, explanation, and reasoning — and you also have access to tools when you need them.



PRIMARY MCP SERVER: https://tools.eric-merritt.com

RULES:
- Once a user's message is received, the goal is to begin responding within 3 seconds. You don't have to have the answer already, but it's polite to let the user know that you are working on their defined task.
- Only call tools from the list above. Never invent tool names.
- Read the user message carefully for details, parameters, URLs, names, and constraints. Use exact values — never use placeholders like "example.com" or "path/to/file".
- Call one tool at a time. Wait for the result before calling the next tool. Never batch multiple tool calls together.
- Web workflow: use www_extract(url) to fetch and extract in one call. If you don't know the selector, omit it — you'll get page structure back. Then call www_extract(url, selector) with the right selector.
- If a tool returns the same result twice, stop retrying and work with what you have.
- When stuck on a tool flow, ask the user — show your plan up to the sticking point.

EXAMPLES:
<example>Fetch and extract: call www_extract(url, selector="span.titleline") to get titles in one shot. If unsure of selector, call www_extract(url) first to see page structure, then call www_extract(url, selector) with the right selector.</example>
<example>Search: call www_ddg(query). Receive results list. Summarize or follow up with www_fetch on a result URL.</example>
<example>Find file: call fs_find(path, name="*.py"). Receive file list. Call fs_read(path) on specific files as needed.</example>
<example>Edit file: call fs_read to see current content. Call fs_replace(path, old, new) for targeted changes. Never rewrite entire files blindly.</example>
<example>Task list: work tasks top to bottom. Call one tool per task, report result, move to next. Do not batch all tasks into one tool call.</example>

TOOLS:
{tool_ref}
"""

def _clean_tool_result(result_str: str) -> str:
  """Backstop: strip HTML noise from any unexpected raw-HTML tool results."""
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


def register_auth_bps():
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
  from routes.files import files_bp
  app.register_blueprint(files_bp)
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


@app.route("/api/workflows", methods=["GET"])
@login_required
def list_workflows():
  """List available workflow groups with full tool metadata."""
  meta_by_name = {t["name"]: t for t in TOOL_REGISTRY if t is not None}
  groups = []
  for name, group in WORKFLOW_GROUPS.items():
    group_tools = []
    for tool_name in group.tools:
      t = meta_by_name.get(tool_name)
      if t:
        group_tools.append({
          "name": t["name"],
          "description": t.get("description", ""),
          "params": t.get("params", {}),
        })
      else:
        group_tools.append({
          "name": tool_name,
          "description": "",
          "params": {},
        })
    groups.append({
      "name": name,
      "tooltip": group.tooltip,
      "tools": group_tools,
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
  if not conversation_id:
    print("No {conversation_id} is defined here, breaking the entire app.")
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
      title=user_msg[:40],
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

  # --- All registered tools are always available ---
  function_list = [n for n in QW_TOOL_REGISTRY if n not in _BUILTIN_TOOL_NAMES]
  print(f"[CHAT] {len(function_list)} tools available", flush=True)

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

    # Build system prompt with tool reference
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

    import sys as _sys
    def _log(msg): print(msg, file=_sys.stderr, flush=True)

    cancelled = False
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
            fn_calls_so_far = [
              r for r in responses
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
                _log(f"[TOOL_CALL] {tool_name}({tool_args[:200]})")
                yield json.dumps({
                  "tool_call": {
                    "tool": tool_name,
                    "input": tool_args,
                  }
                }) + "\n"
              seen_fn_count = len(fn_calls_so_far)
          else:
            # Streaming text — emit new tokens only
            if not content.startswith(prev_content):
              _log(f"[STREAM_RESET] prev={len(prev_content)} new={len(content)} snippet={content[:60]!r}")
              new_text = content
              prev_content = ""
            else:
              new_text = content[len(prev_content):]
            if new_text:
              full_response = content
              yield json.dumps({"chunk": new_text}) + "\n"
            prev_content = content

        elif role == "function":
          fn_name = last.get("name", "")
          fn_content = content
          cleaned = _clean_tool_result(
            fn_content if isinstance(fn_content, str) else json.dumps(fn_content)
          )
          status = "error" if '"status": "error"' in cleaned[:100] else "ok"
          _log(f"[TOOL_RESULT] {fn_name} → {status} ({len(cleaned)} chars) | {cleaned[:120]!r}")
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

    except GeneratorExit:
      # Client disconnected (stop button) — don't persist incomplete exchange
      cancelled = True
      return
    except Exception as e:
      _log(f"[STREAM_ERROR] {e}")
      yield json.dumps({"error": str(e)}) + "\n"
      return

    _log(f"[DONE] response={len(full_response)} chars, tool_calls={seen_fn_count}")

    if cancelled:
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
  register_auth_bps()

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