"""Model registry and runtime model swap."""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from auth.db import get_db
from config import MODELS, SAVE_DIR
from services.llama import (
  MODEL_SWAP_LOCK, kill_llama_server, loaded_model_id, spawn_llama_server,
)

models_bp = Blueprint("models", __name__, url_prefix="/api/models")


@models_bp.route("", methods=["GET"])
@login_required
def list_models():
  """List models known to the registry plus which one is currently loaded."""
  loaded = loaded_model_id()
  prefs = current_user.preferences or {}
  return jsonify({
    "models": list(MODELS.keys()),
    "current": prefs.get("model") or loaded,
    "loaded": loaded,
    "save_dir": SAVE_DIR,
  })


@models_bp.route("", methods=["POST"])
@login_required
def select_model():
  """Switch llama-server to a new model. Body: {"model": "<alias>"}"""
  data = request.get_json(force=True) or {}
  model = (data.get("model") or "").strip()
  if not model:
    return jsonify({"error": "model required"}), 400
  if model not in MODELS:
    return jsonify({"error": f"unknown model '{model}'"}), 400

  with MODEL_SWAP_LOCK:
    if loaded_model_id() != model:
      kill_llama_server()
      if not spawn_llama_server(model):
        return jsonify({"error": "llama-server failed to start"}), 500

  db = get_db()
  prefs = dict(current_user.preferences or {})
  prefs["model"] = model
  current_user.preferences = prefs
  db.commit()
  return jsonify({"model": model, "loaded": model})
