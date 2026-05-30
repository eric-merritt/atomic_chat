import os as _os

from services.logging_setup import configure_logging
configure_logging()

from flask import Flask, jsonify, send_file
from flask_login import login_required, current_user
from qwen_agent.tools.base import TOOL_REGISTRY as QW_TOOL_REGISTRY

_BUILTIN_TOOL_NAMES = set(QW_TOOL_REGISTRY.keys())

import tools  # noqa: F401 — triggers @register_tool side-effects for all tool modules
from pipeline.workflow_groups import WORKFLOW_GROUPS
from auth.middleware import login_manager, auth_guard
from auth.routes import auth_bp, init_oauth
from auth.db import init_db, SessionLocal



app = Flask(__name__)

_FLASK_SECRET_KEY = _os.environ.get("FLASK_SECRET_KEY")
_IS_DEBUG = _os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
if not _FLASK_SECRET_KEY:
  if _IS_DEBUG:
    import secrets as _secrets
    _FLASK_SECRET_KEY = _secrets.token_hex(32)
    print("[warn] FLASK_SECRET_KEY unset — using ephemeral dev key (sessions will not survive restart)", flush=True)
  else:
    raise RuntimeError(
      "FLASK_SECRET_KEY is not set. Refusing to start in non-debug mode without a stable secret key. "
      "Generate one with `python -c 'import secrets; print(secrets.token_hex(32))'` and set it in the environment."
    )
app.secret_key = _FLASK_SECRET_KEY


def _tool_meta(cls) -> dict:
  """Extract name, description, and parameter info from a qwen-agent tool class."""
  schema = getattr(cls, 'parameters', {}) or {}
  props = schema.get('properties', {})
  required = schema.get('required', [])
  params = {}
  for pname, pinfo in props.items():
    entry = {
      'type': pinfo.get('type', 'string'),
      'description': pinfo.get('description', ''),
      'required': pname in required,
    }
    if 'default' in pinfo:
      entry['default'] = pinfo['default']
    params[pname] = entry
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
  from routes.bridge import bridge_bp, sock as bridge_sock
  app.register_blueprint(bridge_bp)
  bridge_sock.init_app(app)
  from routes.health import health_bp
  app.register_blueprint(health_bp)
  from routes.mcp_registry import mcp_registry_bp
  app.register_blueprint(mcp_registry_bp)
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
  """List workflow groups. Non-gated groups in 'groups'; gated groups in 'restricted'."""
  meta_by_name = {t["name"]: t for t in TOOL_REGISTRY if t is not None}
  groups = []
  restricted = []
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
        group_tools.append({"name": tool_name, "description": "", "params": {}})
    entry = {"name": name, "tooltip": group.tooltip, "tools": group_tools}
    if group.gate:
      entry["gate"] = group.gate
      restricted.append(entry)
      prefs = dict(current_user.preferences or {})
      if prefs.get(f"gate_{group.gate}_accepted"):
        groups.append(entry)
    else:
      groups.append(entry)
  return jsonify({"groups": groups, "restricted": restricted})


_HASHED_ASSET_RE = __import__("re").compile(r"\.[A-Za-z0-9_-]{8,}\.(?:js|css|woff2?|png|jpg|jpeg|webp|svg|gif|ico)$")


def _cache_headers_for(path: str) -> dict[str, str]:
  """Vite emits hashed filenames for /assets/* — those are safe to cache forever.
  Everything else (index.html, root assets) gets a short max-age so deploys
  propagate quickly."""
  if path.startswith("assets/") or _HASHED_ASSET_RE.search(path):
    return {"Cache-Control": "public, max-age=31536000, immutable"}
  return {"Cache-Control": "public, max-age=60, must-revalidate"}


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
  """Serve React SPA from frontend/dist/. """
  file_path = _os.path.join(_FRONTEND_DIST, path)
  if path and _os.path.isfile(file_path):
    response = send_file(file_path)
    for header_name, header_value in _cache_headers_for(path).items():
      response.headers[header_name] = header_value
    return response
  index = _os.path.join(_FRONTEND_DIST, "index.html")
  if _os.path.isfile(index):
    response = send_file(index)
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response
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