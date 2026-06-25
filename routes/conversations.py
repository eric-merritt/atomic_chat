"""Conversations API: CRUD + message management + tasks."""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from auth import conv_store as store

conv_bp = Blueprint("conversations", __name__, url_prefix="/api/conversations")


@conv_bp.route("", methods=["POST"])
@login_required
def create_conversation():
    data = request.get_json(force=True)
    conv = store.create_conversation(
        user_id=current_user.id,
        title=data.get("title", "New Conversation")[:255],
        folder=data.get("folder"),
        model=data.get("model"),
    )
    if conv is None:
        return jsonify({"error": "Conversation storage is disabled"}), 503
    return jsonify({"conversation": conv}), 201


@conv_bp.route("", methods=["GET"])
@login_required
def list_conversations():
    result = store.list_conversations(
        user_id=current_user.id,
        folder=request.args.get("folder"),
        search=request.args.get("q", "").strip(),
        page=max(1, request.args.get("page", 1, type=int)),
        limit=min(50, max(1, request.args.get("limit", 20, type=int))),
    )
    return jsonify(result)


@conv_bp.route("/<conv_id>", methods=["GET"])
@login_required
def get_conversation(conv_id):
    result = store.get_conversation(
        user_id=current_user.id,
        conv_id=conv_id,
        page=max(1, request.args.get("page", 1, type=int)),
        limit=min(50, max(1, request.args.get("limit", 20, type=int))),
    )
    if result is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify(result)


@conv_bp.route("/<conv_id>", methods=["PATCH"])
@login_required
def update_conversation(conv_id):
    data = request.get_json(force=True)
    result = store.update_conversation(current_user.id, conv_id, data)
    if result is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"conversation": result})


@conv_bp.route("/<conv_id>", methods=["DELETE"])
@login_required
def delete_conversation(conv_id):
    ok = store.delete_conversation(current_user.id, conv_id)
    if not ok:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"ok": True})


@conv_bp.route("/<conv_id>/messages", methods=["POST"])
@login_required
def add_message(conv_id):
    data = request.get_json(force=True)
    msg = store.add_message(
        user_id=current_user.id,
        conv_id=conv_id,
        role=data.get("role", "user"),
        content=data.get("content", ""),
        images=data.get("images", []),
        tool_calls=data.get("tool_calls", []),
    )
    if msg is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"message": msg}), 201


# ── Tasks ─────────────────────────────────────────────────────────────────────

@conv_bp.route("/<conv_id>/tasks", methods=["GET"])
@login_required
def list_tasks(conv_id):
    tasks = store.list_tasks(current_user.id, conv_id)
    if tasks is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"tasks": tasks})


@conv_bp.route("/<conv_id>/tasks", methods=["POST"])
@login_required
def create_task(conv_id):
    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    task = store.create_task(current_user.id, conv_id, title, data.get("depends_on"))
    if task is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"task": task}), 201


@conv_bp.route("/<conv_id>/tasks/<task_id>", methods=["PATCH"])
@login_required
def update_task(conv_id, task_id):
    data = request.get_json(force=True)
    task = store.update_task(current_user.id, conv_id, task_id, data)
    if task is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"task": task})


@conv_bp.route("/<conv_id>/tasks/<task_id>", methods=["DELETE"])
@login_required
def delete_task(conv_id, task_id):
    ok = store.delete_task(current_user.id, conv_id, task_id)
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"ok": True})


@conv_bp.route("/<conv_id>/tasks/snapshot", methods=["POST"])
@login_required
def snapshot_tasks(conv_id):
    """Fired on TaskList close: hand the current list to the task agent so any
    user-added/edited tasks get decomposed into worker subtasks, just like a task
    typed in chat. `user_added` lists the titles the user entered manually."""
    data = request.get_json(force=True) or {}
    user_added = [t for t in (data.get("user_added") or []) if isinstance(t, str)]

    tasks = store.list_tasks(current_user.id, conv_id)
    if tasks is None:
        return jsonify({"error": "Conversation not found"}), 404

    from agents.agent_taskmgr import queue_user_tasks, run_taskmgr
    queue_user_tasks(conv_id, user_added)
    try:
        run_taskmgr(conv_id, "", tasks)
    except Exception as taskmgr_err:
        # Never fail the close on a taskmgr hiccup; the queue persists for next turn.
        return jsonify({"ok": True, "decomposed": False, "error": str(taskmgr_err)})

    return jsonify({"ok": True, "decomposed": True,
                    "tasks": store.list_tasks(current_user.id, conv_id)})
