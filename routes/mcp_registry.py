"""Curated MCP server registry endpoints.

Exposes the JSON catalog at /api/mcp/servers with optional filtering by
tier (free | freemium | paid) and category. The catalog itself lives in
data/mcp_servers.json so it can be edited without redeploys; mtime caching
keeps the read off the request hot path.
"""

import json
import logging
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask_login import login_required

log = logging.getLogger(__name__)

mcp_registry_bp = Blueprint("mcp_registry", __name__, url_prefix="/api/mcp")

_CATALOG_PATH = Path(__file__).parent.parent / "data" / "mcp_servers.json"
_catalog_cache: dict = {"mtime": -1.0, "data": None}
_catalog_lock = threading.Lock()


def _load_catalog() -> dict:
  """Load mcp_servers.json with mtime-keyed cache."""
  try:
    current_mtime = _CATALOG_PATH.stat().st_mtime
  except OSError:
    log.warning("mcp catalog missing at %s", _CATALOG_PATH)
    return {"schema_version": 1, "servers": [], "categories": []}
  with _catalog_lock:
    if _catalog_cache["mtime"] == current_mtime and _catalog_cache["data"] is not None:
      return _catalog_cache["data"]
    try:
      with open(_CATALOG_PATH, "r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    except Exception as load_err:
      log.error("failed to load mcp catalog: %s", load_err)
      return _catalog_cache["data"] or {"schema_version": 1, "servers": [], "categories": []}
    _catalog_cache["mtime"] = current_mtime
    _catalog_cache["data"] = loaded
    return loaded


def _filter_servers(servers: list[dict], tier: str | None, category: str | None,
                    self_hostable: str | None) -> list[dict]:
  """Apply optional query filters. Returns the filtered list."""
  result = servers
  if tier:
    result = [server for server in result if server.get("tier") == tier]
  if category:
    result = [server for server in result if server.get("category") == category]
  if self_hostable is not None:
    flag_value = self_hostable.lower() in ("1", "true", "yes")
    result = [server for server in result if bool(server.get("self_hostable")) == flag_value]
  return result


@mcp_registry_bp.route("/servers", methods=["GET"])
@login_required
def list_servers():
  """List all known MCP servers with optional filters: tier, category, self_hostable."""
  catalog = _load_catalog()
  filtered = _filter_servers(
    catalog.get("servers", []),
    tier=request.args.get("tier"),
    category=request.args.get("category"),
    self_hostable=request.args.get("self_hostable"),
  )
  return jsonify({
    "schema_version": catalog.get("schema_version", 1),
    "as_of": catalog.get("as_of"),
    "categories": catalog.get("categories", []),
    "count": len(filtered),
    "servers": filtered,
  })


@mcp_registry_bp.route("/servers/<server_id>", methods=["GET"])
@login_required
def get_server(server_id: str):
  """Return one server by id."""
  catalog = _load_catalog()
  for server in catalog.get("servers", []):
    if server.get("id") == server_id:
      return jsonify({"server": server})
  return jsonify({"error": "Server not found", "id": server_id}), 404
