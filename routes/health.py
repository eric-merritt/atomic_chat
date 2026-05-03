"""Health check endpoints.

`/api/health`       — fast liveness probe (always 200 if the Flask process is up).
`/api/health/ready` — readiness probe: checks DB connectivity and llama-server.
                      Returns 200 only when downstream deps respond.
"""

import logging
import time

from flask import Blueprint, jsonify
from sqlalchemy import text

from auth.db import engine
from services.llama import llama_is_healthy, loaded_model_id

log = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__, url_prefix="/api/health")


def _check_db() -> tuple[bool, float, str]:
  """Run SELECT 1 against the configured DB. Returns (ok, latency_ms, error)."""
  started_at = time.monotonic()
  try:
    with engine.connect() as conn:
      conn.execute(text("SELECT 1"))
    return True, (time.monotonic() - started_at) * 1000, ""
  except Exception as db_err:
    return False, (time.monotonic() - started_at) * 1000, str(db_err)[:200]


def _check_llama() -> tuple[bool, float, str | None]:
  """Probe the llama-server /health endpoint and return loaded model id."""
  started_at = time.monotonic()
  alive = llama_is_healthy()
  latency_ms = (time.monotonic() - started_at) * 1000
  return alive, latency_ms, loaded_model_id() if alive else None


@health_bp.route("", methods=["GET"])
def health():
  """Liveness — bare minimum: process is alive and serving HTTP."""
  return jsonify({"status": "ok"})


@health_bp.route("/ready", methods=["GET"])
def ready():
  """Readiness — downstream deps must respond for traffic to be useful."""
  db_ok, db_latency, db_err = _check_db()
  llama_ok, llama_latency, llama_model = _check_llama()
  payload = {
    "status": "ok" if (db_ok and llama_ok) else "degraded",
    "checks": {
      "database": {"ok": db_ok, "latency_ms": round(db_latency, 1), "error": db_err or None},
      "llama_server": {"ok": llama_ok, "latency_ms": round(llama_latency, 1), "model": llama_model},
    },
  }
  status_code = 200 if (db_ok and llama_ok) else 503
  return jsonify(payload), status_code
