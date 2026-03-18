"""Conversations API: CRUD + message management."""

from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_

from auth.db import get_db
from auth.conversations import Conversation, ConversationMessage

conv_bp = Blueprint("conversations", __name__, url_prefix="/api/conversations")


def _conv_json(conv: Conversation, include_messages=False) -> dict:
    d = {
        "id": conv.id,
        "title": conv.title,
        "folder": conv.folder,
        "model": conv.model,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }
    if include_messages:
        d["messages"] = [_msg_json(m) for m in conv.messages]
    return d


def _msg_json(msg: ConversationMessage) -> dict:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "images": msg.images or [],
        "tool_calls": msg.tool_calls or [],
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


@conv_bp.route("", methods=["POST"])
@login_required
def create_conversation():
    data = request.get_json(force=True)
    db = get_db()
    conv = Conversation(
        user_id=current_user.id,
        title=data.get("title", "New Conversation")[:255],
        folder=data.get("folder", None),
        model=data.get("model", None),
    )
    db.add(conv)
    db.commit()
    return jsonify({"conversation": _conv_json(conv)}), 201


@conv_bp.route("", methods=["GET"])
@login_required
def list_conversations():
    db = get_db()
    page = max(1, request.args.get("page", 1, type=int))
    limit = min(50, max(1, request.args.get("limit", 20, type=int)))
    offset = (page - 1) * limit

    q = db.query(Conversation).filter_by(user_id=current_user.id)

    folder = request.args.get("folder")
    if folder:
        q = q.filter_by(folder=folder)

    search = request.args.get("q", "").strip()
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Conversation.title.ilike(pattern),
                Conversation.id.in_(
                    db.query(ConversationMessage.conversation_id)
                    .filter(ConversationMessage.content.ilike(pattern))
                    .subquery()
                ),
            )
        )

    total = q.count()
    conversations = q.order_by(Conversation.updated_at.desc()).offset(offset).limit(limit).all()

    return jsonify({
        "conversations": [_conv_json(c) for c in conversations],
        "total": total,
        "page": page,
        "limit": limit,
    })


@conv_bp.route("/<conv_id>", methods=["GET"])
@login_required
def get_conversation(conv_id):
    db = get_db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=current_user.id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    page = max(1, request.args.get("page", 1, type=int))
    limit = min(50, max(1, request.args.get("limit", 20, type=int)))

    total_messages = db.query(ConversationMessage).filter_by(conversation_id=conv_id).count()
    messages = (
        db.query(ConversationMessage)
        .filter_by(conversation_id=conv_id)
        .order_by(ConversationMessage.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    messages.reverse()  # Return in chronological order

    result = _conv_json(conv)
    result["messages"] = [_msg_json(m) for m in messages]
    result["total_messages"] = total_messages
    result["page"] = page
    result["limit"] = limit
    return jsonify(result)


@conv_bp.route("/<conv_id>", methods=["PATCH"])
@login_required
def update_conversation(conv_id):
    db = get_db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=current_user.id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json(force=True)
    if "title" in data:
        conv.title = data["title"][:255]
    if "folder" in data:
        conv.folder = data["folder"]
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    return jsonify({"conversation": _conv_json(conv)})


@conv_bp.route("/<conv_id>", methods=["DELETE"])
@login_required
def delete_conversation(conv_id):
    db = get_db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=current_user.id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    db.delete(conv)
    db.commit()
    return jsonify({"ok": True})


@conv_bp.route("/<conv_id>/messages", methods=["POST"])
@login_required
def add_message(conv_id):
    db = get_db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=current_user.id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json(force=True)
    msg = ConversationMessage(
        conversation_id=conv_id,
        role=data.get("role", "user"),
        content=data.get("content", ""),
        images=data.get("images", []),
        tool_calls=data.get("tool_calls", []),
    )
    db.add(msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    return jsonify({"message": _msg_json(msg)}), 201
