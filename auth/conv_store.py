"""Conversation storage dispatcher.

Reads CONVERSATION_STORAGE env var and delegates to the right backend:
  sqlite  — SQLAlchemy + SQLite/PostgreSQL (default)
  jsonl   — flat JSONL files per conversation
  none    — no persistence; all operations return empty/stub data
"""

import os

_STORAGE = os.environ.get("CONVERSATION_STORAGE", "sqlite").lower()


def _db():
    from auth.db import get_db as _get_db
    return _get_db()


# ── Conversations ─────────────────────────────────────────────────────────────

def create_conversation(user_id, title, folder=None, model=None):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import create_conversation as _c
        return _c(user_id, title, folder, model)
    if _STORAGE == "none":
        return None

    from auth.conversations import Conversation
    db = _db()
    conv = Conversation(user_id=user_id, title=(title or "New Conversation")[:255],
                        folder=folder, model=model)
    db.add(conv); db.commit()
    return _conv_to_dict(conv)


def list_conversations(user_id, folder=None, search="", page=1, limit=20):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import list_conversations as _l
        return _l(user_id, folder=folder, search=search, page=page, limit=limit)
    if _STORAGE == "none":
        return {"conversations": [], "total": 0, "page": page, "limit": limit}

    from auth.conversations import Conversation, ConversationMessage
    from sqlalchemy import or_
    db = _db()
    q = db.query(Conversation).filter_by(user_id=user_id)
    if folder:
        q = q.filter_by(folder=folder)
    if search:
        pat = f"%{search}%"
        q = q.filter(or_(
            Conversation.title.ilike(pat),
            Conversation.id.in_(
                db.query(ConversationMessage.conversation_id)
                .filter(ConversationMessage.content.ilike(pat)).subquery()
            ),
        ))
    total = q.count()
    convs = q.order_by(Conversation.updated_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return {"conversations": [_conv_to_dict(c) for c in convs], "total": total, "page": page, "limit": limit}


def get_conversation(user_id, conv_id, page=1, limit=20):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import get_conversation as _g
        return _g(user_id, conv_id, page=page, limit=limit)
    if _STORAGE == "none":
        return None

    from auth.conversations import Conversation, ConversationMessage
    db = _db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return None
    total = db.query(ConversationMessage).filter_by(conversation_id=conv_id).count()
    msgs = (db.query(ConversationMessage).filter_by(conversation_id=conv_id)
            .order_by(ConversationMessage.created_at.desc())
            .offset((page - 1) * limit).limit(limit).all())
    msgs.reverse()
    result = _conv_to_dict(conv)
    result["messages"] = [_msg_to_dict(m) for m in msgs]
    result["total_messages"] = total
    result["page"] = page
    result["limit"] = limit
    return result


def update_conversation(user_id, conv_id, data):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import update_conversation as _u
        return _u(user_id, conv_id, data)
    if _STORAGE == "none":
        return None

    from auth.conversations import Conversation
    from datetime import datetime, timezone
    db = _db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return None
    if "title" in data:
        conv.title = data["title"][:255]
    if "folder" in data:
        conv.folder = data["folder"]
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _conv_to_dict(conv)


def delete_conversation(user_id, conv_id):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import delete_conversation as _d
        return _d(user_id, conv_id)
    if _STORAGE == "none":
        return False

    from auth.conversations import Conversation
    db = _db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return False
    db.delete(conv); db.commit()
    return True


def add_message(user_id, conv_id, role, content, images=None, tool_calls=None):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import add_message as _a
        return _a(user_id, conv_id, role, content, images or [], tool_calls or [])
    if _STORAGE == "none":
        return None

    from auth.conversations import Conversation, ConversationMessage
    from datetime import datetime, timezone
    db = _db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return None
    msg = ConversationMessage(conversation_id=conv_id, role=role, content=content,
                               images=images or [], tool_calls=tool_calls or [])
    db.add(msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _msg_to_dict(msg)


# ── Tasks ─────────────────────────────────────────────────────────────────────

def list_tasks(user_id, conv_id):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import list_tasks as _l
        return _l(user_id, conv_id)
    if _STORAGE == "none":
        return []

    from auth.conversations import Conversation
    from auth.conversation_tasks import ConversationTask
    db = _db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return None
    tasks = (db.query(ConversationTask).filter_by(conversation_id=conv_id)
             .order_by(ConversationTask.created_at.asc()).all())
    return [_task_to_dict(t) for t in tasks]


def create_task(user_id, conv_id, title, depends_on=None):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import create_task as _c
        return _c(user_id, conv_id, title, depends_on)
    if _STORAGE == "none":
        return None

    from auth.conversations import Conversation
    from auth.conversation_tasks import ConversationTask
    db = _db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return None
    task = ConversationTask(conversation_id=conv_id, title=title, depends_on=depends_on)
    db.add(task); db.commit()
    return _task_to_dict(task)


def update_task(user_id, conv_id, task_id, data):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import update_task as _u
        return _u(user_id, conv_id, task_id, data)
    if _STORAGE == "none":
        return None

    from auth.conversations import Conversation
    from auth.conversation_tasks import ConversationTask
    db = _db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return None
    task = db.query(ConversationTask).filter_by(id=task_id, conversation_id=conv_id).first()
    if not task:
        return None
    for k in ("title", "status", "depends_on"):
        if k in data:
            setattr(task, k, data[k])
    db.commit()
    return _task_to_dict(task)


def delete_task(user_id, conv_id, task_id):
    if _STORAGE == "jsonl":
        from auth.conversations_jsonl import delete_task as _d
        return _d(user_id, conv_id, task_id)
    if _STORAGE == "none":
        return False

    from auth.conversations import Conversation
    from auth.conversation_tasks import ConversationTask
    db = _db()
    conv = db.query(Conversation).filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return False
    task = db.query(ConversationTask).filter_by(id=task_id, conversation_id=conv_id).first()
    if not task:
        return False
    db.delete(task); db.commit()
    return True


# ── Serialisers ───────────────────────────────────────────────────────────────

def _conv_to_dict(conv) -> dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "folder": conv.folder,
        "model": conv.model,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }


def _msg_to_dict(msg) -> dict:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "images": msg.images or [],
        "tool_calls": msg.tool_calls or [],
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def _task_to_dict(task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "depends_on": task.depends_on,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
