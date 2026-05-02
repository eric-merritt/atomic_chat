import os as _os
from dotenv import load_dotenv
load_dotenv(override=True)

import requests
from flask import Flask, jsonify, send_file
from flask_login import login_required
import json5
from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool, TOOL_REGISTRY as QW_TOOL_REGISTRY

_BUILTIN_TOOL_NAMES = set(QW_TOOL_REGISTRY.keys())

import tools  # triggers @register_tool side-effects for all tool modules
import tools.native as native_tools
from config import qwen_llm_cfg, LLAMA_SERVER_URL
from pipeline.workflow_groups import WORKFLOW_GROUPS, TOOL_REF
from auth.middleware import login_manager, auth_guard
from auth.routes import auth_bp, init_oauth
from auth.db import init_db, SessionLocal

LLAMA_CPP_BASE_URL = LLAMA_SERVER_URL



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
  from routes.chat import chat_bp
  app.register_blueprint(chat_bp)
  from routes.models import models_bp
  app.register_blueprint(models_bp)
  app.before_request(auth_guard)

@app.teardown_appcontext
def shutdown_session(exception=None):
  SessionLocal.remove()

# Create tables on first run (use Alembic migrations in production)
with app.app_context():
  init_db()

_FRONTEND_DIST = _os.path.join(_os.path.dirname(__file__), "frontend", "dist")





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


# Populate TOOL_REGISTRY now that all tools (including internal) are registered
TOOL_REGISTRY = [_tool_meta(cls) for cls in QW_TOOL_REGISTRY.values()
  if cls.name not in _BUILTIN_TOOL_NAMES]


# ─────────────────────────────────────────────────────────────
# STREAMING CHAT       → routes/chat.py
# MODEL REGISTRY/SWAP  → routes/models.py
# LLAMA SUBPROCESS     → services/llama.py
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────

def main():
  import sys
  register_auth_bps()

  port = 5000
  for arg in sys.argv:
    if arg.startswith("--port="):
      port = int(arg.split("=")[1])

  print(f"Starting server on http://localhost:{port}")
  app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
  main()