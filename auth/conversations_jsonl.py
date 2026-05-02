"""JSONL-based conversation storage backend.

Layout:
  {JSONL_PATH}/{user_id}/{conv_id}.jsonl      — one JSON line per message
  {JSONL_PATH}/{user_id}/{conv_id}.meta.json  — conversation metadata + tasks
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

JSONL_PATH = Path(os.environ.get("JSONL_PATH", Path.home() / ".atomic_chat" / "conversations"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


def _user_dir(user_id: str) -> Path:
    d = JSONL_PATH / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _meta_path(user_id: str, conv_id: str) -> Path:
    return _user_dir(user_id) / f"{conv_id}.meta.json"


def _jsonl_path(user_id: str, conv_id: str) -> Path:
    return _user_dir(user_id) / f"{conv_id}.jsonl"


def _read_meta(user_id: str, conv_id: str) -> dict | None:
    p = _meta_path(user_id, conv_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _write_meta(user_id: str, conv_id: str, meta: dict):
    _meta_path(user_id, conv_id).write_text(json.dumps(meta, indent=2))


def _read_messages(user_id: str, conv_id: str) -> list[dict]:
    p = _jsonl_path(user_id, conv_id)
    if not p.exists():
        return []
    msgs = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                msgs.append(json.loads(line))
            except Exception:
                pass
    return msgs


# ── Conversations ─────────────────────────────────────────────────────────────

def create_conversation(user_id: str, title: str, folder: str | None, model: str | None) -> dict:
    conv_id = _uid()
    now = _now()
    meta = {
        "id": conv_id,
        "user_id": user_id,
        "title": title or "New Conversation",
        "folder": folder,
        "model": model,
        "created_at": now,
        "updated_at": now,
        "tasks": [],
    }
    _write_meta(user_id, conv_id, meta)
    _jsonl_path(user_id, conv_id).touch()
    return meta


def list_conversations(user_id: str, folder: str | None = None,
                       search: str = "", page: int = 1, limit: int = 20) -> dict:
    d = _user_dir(user_id)
    metas = []
    for p in d.glob("*.meta.json"):
        try:
            m = json.loads(p.read_text())
            metas.append(m)
        except Exception:
            pass

    if folder:
        metas = [m for m in metas if m.get("folder") == folder]

    if search:
        s = search.lower()
        filtered = []
        for m in metas:
            if s in m.get("title", "").lower():
                filtered.append(m)
                continue
            for msg in _read_messages(user_id, m["id"]):
                if s in msg.get("content", "").lower():
                    filtered.append(m)
                    break
        metas = filtered

    metas.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
    total = len(metas)
    offset = (page - 1) * limit
    return {"conversations": metas[offset:offset + limit], "total": total, "page": page, "limit": limit}


def get_conversation(user_id: str, conv_id: str, page: int = 1, limit: int = 20) -> dict | None:
    meta = _read_meta(user_id, conv_id)
    if not meta:
        return None
    all_msgs = _read_messages(user_id, conv_id)
    total = len(all_msgs)
    offset = (page - 1) * limit
    msgs = all_msgs[max(0, total - offset - limit):total - offset] if offset else all_msgs[-limit:]
    result = dict(meta)
    result["messages"] = msgs
    result["total_messages"] = total
    result["page"] = page
    result["limit"] = limit
    return result


def update_conversation(user_id: str, conv_id: str, data: dict) -> dict | None:
    meta = _read_meta(user_id, conv_id)
    if not meta:
        return None
    if "title" in data:
        meta["title"] = data["title"][:255]
    if "folder" in data:
        meta["folder"] = data["folder"]
    meta["updated_at"] = _now()
    _write_meta(user_id, conv_id, meta)
    return meta


def delete_conversation(user_id: str, conv_id: str) -> bool:
    mp = _meta_path(user_id, conv_id)
    jp = _jsonl_path(user_id, conv_id)
    if not mp.exists():
        return False
    mp.unlink(missing_ok=True)
    jp.unlink(missing_ok=True)
    return True


# ── Messages ──────────────────────────────────────────────────────────────────

def add_message(user_id: str, conv_id: str, role: str, content: str,
                images: list, tool_calls: list) -> dict | None:
    meta = _read_meta(user_id, conv_id)
    if not meta:
        return None
    msg = {
        "id": _uid(),
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "images": images or [],
        "tool_calls": tool_calls or [],
        "created_at": _now(),
    }
    with open(_jsonl_path(user_id, conv_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(msg) + "\n")
    meta["updated_at"] = _now()
    _write_meta(user_id, conv_id, meta)
    return msg


# ── Tasks ─────────────────────────────────────────────────────────────────────

def list_tasks(user_id: str, conv_id: str) -> list[dict] | None:
    meta = _read_meta(user_id, conv_id)
    if meta is None:
        return None
    return sorted(meta.get("tasks", []), key=lambda t: t.get("created_at", ""))


def create_task(user_id: str, conv_id: str, title: str, depends_on: str | None) -> dict | None:
    meta = _read_meta(user_id, conv_id)
    if not meta:
        return None
    task = {
        "id": _uid(),
        "title": title,
        "status": "pending",
        "depends_on": depends_on,
        "created_at": _now(),
    }
    meta.setdefault("tasks", []).append(task)
    _write_meta(user_id, conv_id, meta)
    return task


def update_task(user_id: str, conv_id: str, task_id: str, data: dict) -> dict | None:
    meta = _read_meta(user_id, conv_id)
    if not meta:
        return None
    for task in meta.get("tasks", []):
        if task["id"] == task_id:
            for k in ("title", "status", "depends_on"):
                if k in data:
                    task[k] = data[k]
            _write_meta(user_id, conv_id, meta)
            return task
    return None


def delete_task(user_id: str, conv_id: str, task_id: str) -> bool:
    meta = _read_meta(user_id, conv_id)
    if not meta:
        return False
    tasks = meta.get("tasks", [])
    new_tasks = [t for t in tasks if t["id"] != task_id]
    if len(new_tasks) == len(tasks):
        return False
    meta["tasks"] = new_tasks
    _write_meta(user_id, conv_id, meta)
    return True
