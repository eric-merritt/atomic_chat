# User Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a user dashboard with conversation persistence, profile management, API keys UI, and per-user preferences.

**Architecture:** Single-page dashboard at `/dashboard` with left nav and swappable panels. Conversations persist to PostgreSQL with backend-driven streaming persistence. User preferences (theme, save mode, tools) stored as JSONB on the users table and loaded on auth.

**Tech Stack:** Flask, SQLAlchemy (PostgreSQL/JSONB), React 19, React Router 7, Tailwind CSS, existing atomic design pattern.

**Spec:** `docs/superpowers/specs/2026-03-17-user-dashboard-design.md`

---

## File Structure

### Backend (new files)
- `auth/conversations.py` — Conversation + ConversationMessage models
- `routes/conversations.py` — Conversations blueprint (CRUD + messages)
- `routes/preferences.py` — Preferences + profile + password endpoints

### Backend (modified files)
- `auth/models.py` — Add `preferences` JSONB column to User
- `auth/routes.py` — Add `preferences` to `_user_json`
- `auth/db.py` — No changes needed (models auto-register via Base)
- `main.py` — Register new blueprints, modify `/api/chat/stream` to accept `conversation_id`, make tool selection per-user

### Frontend (new files)
- `frontend/src/atoms/conversation.ts` — Conversation + Preferences types
- `frontend/src/api/conversations.ts` — Conversations API adapter
- `frontend/src/api/preferences.ts` — Preferences API adapter
- `frontend/src/components/atoms/Avatar.tsx` — User avatar component
- `frontend/src/components/atoms/Modal.tsx` — Reusable modal overlay
- `frontend/src/components/atoms/DropdownMenu.tsx` — Positioned dropdown
- `frontend/src/components/molecules/UserMenu.tsx` — Avatar + dropdown
- `frontend/src/components/molecules/ConversationItem.tsx` — List row
- `frontend/src/components/molecules/ConversationTitle.tsx` — Title + pencil
- `frontend/src/components/molecules/NewConversationButton.tsx` — Top of chat
- `frontend/src/components/molecules/SaveConversationModal.tsx` — Save/discard
- `frontend/src/components/molecules/ApiKeyRow.tsx` — Key table row
- `frontend/src/components/molecules/CreateKeyModal.tsx` — Key creation
- `frontend/src/components/organisms/DashboardNav.tsx` — Left nav
- `frontend/src/components/organisms/ConversationList.tsx` — Search + list
- `frontend/src/components/organisms/ProfilePanel.tsx` — Profile stub
- `frontend/src/components/organisms/ApiKeyPanel.tsx` — Key management
- `frontend/src/components/organisms/ConnectionsPanel.tsx` — Stub
- `frontend/src/pages/DashboardPage.tsx` — Dashboard layout
- `frontend/src/providers/PreferencesProvider.tsx` — Preferences context

### Frontend (modified files)
- `frontend/src/atoms/user.ts` — Add Preferences type
- `frontend/src/App.tsx` — Add `/dashboard` route, add PreferencesProvider
- `frontend/src/components/organisms/TopBar.tsx` — Replace logout with UserMenu
- `frontend/src/providers/ChatProvider.tsx` — Add conversation_id tracking, save mode logic
- `frontend/src/providers/ThemeProvider.tsx` — Read initial theme from preferences
- `frontend/src/api/chat.ts` — Pass conversation_id to stream
- `frontend/src/components/organisms/MessageList.tsx` — Add ConversationTitle, NewConversationButton

---

## Phase 1: Database & Backend API

### Task 1: Add preferences column to User model

**Files:**
- Modify: `auth/models.py`

- [ ] **Step 1: Add JSONB import and preferences column**

In `auth/models.py`, add `JSONB` import and column to User:

```python
# Add to imports (line 6):
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
```

```python
# Add to User class, after avatar_url (line 37):
    preferences = Column(JSONB, nullable=False, default=dict, server_default='{}')
```

- [ ] **Step 2: Add preferences to _user_json**

In `auth/routes.py`, modify `_user_json` (line 43):

```python
def _user_json(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "auth_method": user.auth_method,
        "preferences": user.preferences or {},
    }
```

- [ ] **Step 3: Restart server to auto-create column**

Run: `pkill -f "python.*main.py"; sleep 2 && source .venv/bin/activate && source .env && python main.py --serve`

The `init_db()` call in main.py will add the new column.

- [ ] **Step 4: Verify column exists**

```bash
source .venv/bin/activate && source .env && python3 -c "
from auth.db import get_db, init_db
from auth.models import User
from main import app
with app.app_context():
    init_db()
    db = get_db()
    u = db.query(User).first()
    print(f'preferences: {u.preferences}')
"
```

- [ ] **Step 5: Commit**

```bash
git add auth/models.py auth/routes.py
git commit -m "feat: add preferences JSONB column to User model"
```

---

### Task 2: Add Conversation and ConversationMessage models

**Files:**
- Create: `auth/conversations.py`

- [ ] **Step 1: Create conversation models**

```python
"""SQLAlchemy models for conversations."""

from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from auth.models import Base, _uuid, _now


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False, default="New Conversation")
    folder = Column(String(128), nullable=True)
    model = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User")
    messages = relationship("ConversationMessage", back_populates="conversation",
                            cascade="all, delete-orphan", order_by="ConversationMessage.created_at")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False, default="")
    images = Column(JSONB, nullable=False, default=list, server_default='[]')
    tool_calls = Column(JSONB, nullable=False, default=list, server_default='[]')
    created_at = Column(DateTime(timezone=True), default=_now)

    conversation = relationship("Conversation", back_populates="messages")
```

- [ ] **Step 2: Import in main.py so tables are created**

In `main.py`, add after the auth imports (around line 160):

```python
import auth.conversations  # register conversation models with Base
```

- [ ] **Step 3: Restart server, verify tables created**

```bash
pkill -f "python.*main.py"; sleep 2 && source .venv/bin/activate && source .env && python -c "
from main import app
from auth.db import get_db
with app.app_context():
    db = get_db()
    result = db.execute(db.bind.raw_connection().cursor().execute('SELECT 1 FROM conversations LIMIT 0'))
    print('conversations table exists')
"
```

- [ ] **Step 4: Commit**

```bash
git add auth/conversations.py main.py
git commit -m "feat: add Conversation and ConversationMessage models"
```

---

### Task 3: Conversations API endpoints

**Files:**
- Create: `routes/conversations.py`
- Modify: `main.py` (register blueprint)
- Modify: `auth/middleware.py` (add public paths if needed)

- [ ] **Step 1: Create conversations blueprint**

Create `routes/` directory and `routes/__init__.py` (empty), then `routes/conversations.py`:

```python
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
```

- [ ] **Step 2: Register blueprint in main.py**

After the auth blueprint registration (around line 166):

```python
from routes.conversations import conv_bp
app.register_blueprint(conv_bp)
```

- [ ] **Step 3: Test endpoints with curl**

```bash
# Create conversation
curl -s -b cookies.txt -c cookies.txt http://localhost:5000/api/conversations -X POST -H 'Content-Type: application/json' -d '{"title":"Test Chat","model":"llama3"}'

# List conversations
curl -s -b cookies.txt http://localhost:5000/api/conversations
```

- [ ] **Step 4: Commit**

```bash
git add routes/__init__.py routes/conversations.py main.py
git commit -m "feat: add conversations API with CRUD and pagination"
```

---

### Task 4: Preferences, profile, and password endpoints

**Files:**
- Create: `routes/preferences.py`
- Modify: `main.py` (register blueprint)

- [ ] **Step 1: Create preferences blueprint**

```python
"""User preferences, profile, and password management."""

import bcrypt
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from auth.db import get_db
from auth.models import User

prefs_bp = Blueprint("preferences", __name__, url_prefix="/api/auth")


@prefs_bp.route("/preferences", methods=["GET"])
@login_required
def get_preferences():
    return jsonify({"preferences": current_user.preferences or {}})


@prefs_bp.route("/preferences", methods=["PATCH"])
@login_required
def update_preferences():
    data = request.get_json(force=True)
    db = get_db()
    prefs = dict(current_user.preferences or {})
    prefs.update(data)
    current_user.preferences = prefs
    db.commit()
    return jsonify({"preferences": current_user.preferences})


@prefs_bp.route("/profile", methods=["PATCH"])
@login_required
def update_profile():
    data = request.get_json(force=True)
    db = get_db()

    if "username" in data:
        username = data["username"].strip()
        if len(username) < 3 or len(username) > 64:
            return jsonify({"error": "Username must be 3-64 characters"}), 400
        existing = db.query(User).filter_by(username=username).first()
        if existing and existing.id != current_user.id:
            return jsonify({"error": "Username already taken"}), 409
        current_user.username = username

    if "email" in data:
        email = data["email"].strip() or None
        if email:
            existing = db.query(User).filter_by(email=email).first()
            if existing and existing.id != current_user.id:
                return jsonify({"error": "Email already registered"}), 409
        current_user.email = email

    db.commit()
    return jsonify({"user": {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "avatar_url": current_user.avatar_url,
        "auth_method": current_user.auth_method,
        "preferences": current_user.preferences or {},
    }})


@prefs_bp.route("/password", methods=["POST"])
@login_required
def change_password():
    if current_user.auth_method != "local":
        return jsonify({"error": "Password change not available for OAuth accounts"}), 403

    data = request.get_json(force=True)
    current_pw = data.get("current_password", "")
    new_pw = data.get("new_password", "")

    if not current_pw or not new_pw:
        return jsonify({"error": "Both current and new password required"}), 400

    if not bcrypt.checkpw(current_pw.encode(), current_user.password_hash.encode()):
        return jsonify({"error": "Current password is incorrect"}), 400

    if len(new_pw) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    db = get_db()
    current_user.password_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt(12)).decode()
    db.commit()
    return jsonify({"ok": True})
```

- [ ] **Step 2: Register blueprint in main.py**

```python
from routes.preferences import prefs_bp
app.register_blueprint(prefs_bp)
```

- [ ] **Step 3: Test preferences endpoint**

```bash
curl -s -b cookies.txt http://localhost:5000/api/auth/preferences -X PATCH -H 'Content-Type: application/json' -d '{"save_mode":"auto","theme":"cyber-dark"}'
```

- [ ] **Step 4: Commit**

```bash
git add routes/preferences.py main.py
git commit -m "feat: add preferences, profile, and password endpoints"
```

---

### Task 5: Modify /api/chat/stream for conversation persistence

**Files:**
- Modify: `main.py` — stream endpoint to accept conversation_id and persist messages

- [ ] **Step 1: Update stream endpoint**

In `main.py`, modify the `/api/chat/stream` handler to:
1. Accept optional `conversation_id` in request body
2. If present, persist user message before streaming
3. After stream completes, persist assistant message
4. If no conversation_id but user has auto save mode, create conversation first

Find the stream endpoint (around line 485) and update the request parsing:

```python
@app.route("/api/chat/stream", methods=["POST"])
@login_required
def chat_stream():
    data = request.get_json(force=True)
    user_msg = data.get("message", "")
    conversation_id = data.get("conversation_id")

    # Auto-create conversation if save_mode is auto and no conversation_id
    if not conversation_id and current_user.preferences and current_user.preferences.get("save_mode") == "auto":
        from auth.conversations import Conversation
        db = get_db()
        conv = Conversation(
            user_id=current_user.id,
            title=user_msg[:50] if user_msg else "New Conversation",
            model=_state.get("model"),
        )
        db.add(conv)
        db.commit()
        conversation_id = conv.id

    # Persist user message
    if conversation_id:
        from auth.conversations import Conversation, ConversationMessage
        db = get_db()
        conv = db.query(Conversation).filter_by(id=conversation_id, user_id=current_user.id).first()
        if conv:
            db.add(ConversationMessage(
                conversation_id=conversation_id,
                role="user",
                content=user_msg,
            ))
            conv.updated_at = _datetime.now(_timezone.utc)
            db.commit()
```

Then at the end of the generator, after `full_response` is assembled, persist the assistant message:

```python
    # At end of generator, after yielding done:
    if conversation_id:
        from auth.conversations import ConversationMessage
        db = get_db()
        db.add(ConversationMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=full_response,
            images=images_collected,
            tool_calls=tool_calls_collected,
        ))
        db.commit()
```

Also emit conversation_id in the first stream event so the frontend can track it:

```python
    # First event in stream:
    yield json.dumps({"type": "meta", "conversation_id": conversation_id}) + "\n"
```

- [ ] **Step 2: Test streaming with conversation_id**

```bash
curl -s -b cookies.txt -N http://localhost:5000/api/chat/stream -X POST -H 'Content-Type: application/json' -d '{"message":"hello","conversation_id":null}'
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: persist messages during streaming with conversation_id"
```

---

### Task 6: Per-user tool selection

**Files:**
- Modify: `main.py` — tool select/deselect endpoints read/write user preferences

- [ ] **Step 1: Update tool select/deselect endpoints**

Replace the current global `_state["selected_tools"]` logic in `/api/tools/select` and `/api/tools/deselect` to read/write from the user's `preferences.selected_tools`:

```python
@app.route("/api/tools/select", methods=["POST"])
@login_required
def select_tool():
    data = request.get_json(force=True)
    tool_name = data.get("name")
    if not tool_name:
        return jsonify({"error": "name required"}), 400

    db = get_db()
    prefs = dict(current_user.preferences or {})
    selected = list(prefs.get("selected_tools", []))
    if tool_name not in selected:
        selected.append(tool_name)
    prefs["selected_tools"] = selected
    current_user.preferences = prefs
    db.commit()
    return get_tools()
```

Similar for deselect. Also update `get_tools()` to read from user preferences.

- [ ] **Step 2: Update `/api/chat/stream` to use per-user tools**

Read selected tools from `current_user.preferences.get("selected_tools", DEFAULT_TOOLS)` instead of `_state["selected_tools"]`.

- [ ] **Step 3: Test tool selection persists per-user**

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: per-user tool selection via preferences"
```

---

## Phase 2: Frontend Foundation (Atoms, Types, Providers)

### Task 7: Frontend types and API adapters

**Files:**
- Modify: `frontend/src/atoms/user.ts`
- Create: `frontend/src/atoms/conversation.ts`
- Create: `frontend/src/api/conversations.ts`
- Create: `frontend/src/api/preferences.ts`

- [ ] **Step 1: Update User type and add Preferences**

In `frontend/src/atoms/user.ts`:

```typescript
export type Role = 'admin' | 'user' | 'viewer';
export type SaveMode = 'auto' | 'prompt' | 'never';

export interface Preferences {
  save_mode?: SaveMode;
  theme?: string;
  selected_tools?: string[];
}

export interface User {
  id: string;
  username: string;
  email: string | null;
  role: Role;
  avatar_url: string | null;
  auth_method: 'local' | 'oauth';
  preferences?: Preferences;
}
```

- [ ] **Step 2: Create conversation types**

Create `frontend/src/atoms/conversation.ts`:

```typescript
export interface Conversation {
  id: string;
  title: string;
  folder: string | null;
  model: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  content: string;
  images: { src: string; filename: string; sizeKb: number }[];
  tool_calls: { tool: string; input: string }[];
  created_at: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  page: number;
  limit: number;
}
```

- [ ] **Step 3: Create conversations API adapter**

Create `frontend/src/api/conversations.ts`:

```typescript
const OPTS: RequestInit = { credentials: 'include' };
const HEADERS = { 'Content-Type': 'application/json' };

export async function listConversations(params?: { q?: string; folder?: string; page?: number; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.q) sp.set('q', params.q);
  if (params?.folder) sp.set('folder', params.folder);
  if (params?.page) sp.set('page', String(params.page));
  if (params?.limit) sp.set('limit', String(params.limit));
  const resp = await fetch(`/api/conversations?${sp}`, OPTS);
  return resp.json();
}

export async function getConversation(id: string, page = 1, limit = 20) {
  const resp = await fetch(`/api/conversations/${id}?page=${page}&limit=${limit}`, OPTS);
  return resp.json();
}

export async function createConversation(title: string, model?: string, folder?: string) {
  const resp = await fetch('/api/conversations', {
    ...OPTS, method: 'POST', headers: HEADERS,
    body: JSON.stringify({ title, model, folder }),
  });
  return resp.json();
}

export async function updateConversation(id: string, data: { title?: string; folder?: string }) {
  const resp = await fetch(`/api/conversations/${id}`, {
    ...OPTS, method: 'PATCH', headers: HEADERS,
    body: JSON.stringify(data),
  });
  return resp.json();
}

export async function deleteConversation(id: string) {
  await fetch(`/api/conversations/${id}`, { ...OPTS, method: 'DELETE' });
}
```

- [ ] **Step 4: Create preferences API adapter**

Create `frontend/src/api/preferences.ts`:

```typescript
import type { Preferences } from '../atoms/user';

const OPTS: RequestInit = { credentials: 'include' };
const HEADERS = { 'Content-Type': 'application/json' };

export async function getPreferences(): Promise<Preferences> {
  const resp = await fetch('/api/auth/preferences', OPTS);
  const data = await resp.json();
  return data.preferences || {};
}

export async function updatePreferences(prefs: Partial<Preferences>): Promise<Preferences> {
  const resp = await fetch('/api/auth/preferences', {
    ...OPTS, method: 'PATCH', headers: HEADERS,
    body: JSON.stringify(prefs),
  });
  const data = await resp.json();
  return data.preferences;
}

export async function updateProfile(data: { username?: string; email?: string }) {
  const resp = await fetch('/api/auth/profile', {
    ...OPTS, method: 'PATCH', headers: HEADERS,
    body: JSON.stringify(data),
  });
  return resp.json();
}

export async function changePassword(currentPassword: string, newPassword: string) {
  const resp = await fetch('/api/auth/password', {
    ...OPTS, method: 'POST', headers: HEADERS,
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return resp.json();
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/atoms/user.ts frontend/src/atoms/conversation.ts frontend/src/api/conversations.ts frontend/src/api/preferences.ts
git commit -m "feat: add conversation and preferences types and API adapters"
```

---

### Task 8: Reusable atoms (Avatar, Modal, DropdownMenu)

**Files:**
- Create: `frontend/src/components/atoms/Avatar.tsx`
- Create: `frontend/src/components/atoms/Modal.tsx`
- Create: `frontend/src/components/atoms/DropdownMenu.tsx`

- [ ] **Step 1: Create Avatar atom**

```typescript
// Avatar.tsx
import { Icon } from './Icon';

interface AvatarProps {
  src?: string | null;
  alt?: string;
  size?: number;
  className?: string;
}

export function Avatar({ src, alt = '', size = 32, className = '' }: AvatarProps) {
  if (src) {
    return <img src={src} alt={alt} width={size} height={size} className={`rounded-full object-cover ${className}`} />;
  }
  return (
    <div
      className={`rounded-full bg-[var(--msg-user)] flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
    >
      <Icon name="user" size={size * 0.6} className="text-[var(--accent)]" />
    </div>
  );
}
```

Note: Add a `user` icon to `Icon.tsx`:
```typescript
user: (
  <>
    <circle cx="12" cy="8" r="4" />
    <path d="M20 21a8 8 0 10-16 0" />
  </>
),
```

- [ ] **Step 2: Create Modal atom**

```typescript
// Modal.tsx
import { useEffect } from 'react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}

export function Modal({ open, onClose, children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative z-10 bg-[var(--glass-bg-solid)] border border-[var(--accent)] rounded-2xl p-6 shadow-[0_8px_32px_rgba(0,0,0,0.3)] max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create DropdownMenu atom**

```typescript
// DropdownMenu.tsx
import { useEffect, useRef } from 'react';

interface MenuItem {
  label: string;
  onClick: () => void;
}

interface DropdownMenuProps {
  items: MenuItem[];
  open: boolean;
  onClose: () => void;
  className?: string;
}

export function DropdownMenu({ items, open, onClose, className = '' }: DropdownMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={ref}
      className={`absolute z-50 bg-[var(--glass-bg-solid)] border border-[var(--accent)] rounded-lg shadow-lg overflow-hidden ${className}`}
    >
      {items.map((item) => (
        <button
          key={item.label}
          onClick={() => { item.onClick(); onClose(); }}
          className="w-full text-left px-4 py-2 text-sm text-[var(--text)] hover:bg-[var(--msg-user)] transition-colors cursor-pointer"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/atoms/Avatar.tsx frontend/src/components/atoms/Modal.tsx frontend/src/components/atoms/DropdownMenu.tsx frontend/src/components/atoms/Icon.tsx
git commit -m "feat: add Avatar, Modal, and DropdownMenu atoms"
```

---

### Task 9: PreferencesProvider and provider wiring

**Files:**
- Create: `frontend/src/providers/PreferencesProvider.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/providers/ThemeProvider.tsx`

- [ ] **Step 1: Create PreferencesProvider**

```typescript
// PreferencesProvider.tsx
import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import type { Preferences } from '../atoms/user';
import { updatePreferences as apiUpdatePrefs } from '../api/preferences';
import { useAuth } from '../hooks/useAuth';

interface PreferencesContextValue {
  preferences: Preferences;
  updatePreferences: (prefs: Partial<Preferences>) => Promise<void>;
}

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [preferences, setPreferences] = useState<Preferences>({});

  useEffect(() => {
    if (user?.preferences) setPreferences(user.preferences);
  }, [user]);

  const updatePreferences = useCallback(async (prefs: Partial<Preferences>) => {
    const updated = await apiUpdatePrefs(prefs);
    setPreferences(updated);
  }, []);

  return (
    <PreferencesContext.Provider value={{ preferences, updatePreferences }}>
      {children}
    </PreferencesContext.Provider>
  );
}

export function usePreferences() {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error('usePreferences must be used within PreferencesProvider');
  return ctx;
}
```

- [ ] **Step 2: Wire into App.tsx**

Add `PreferencesProvider` wrapping `ThemeProvider` inside AuthGate:

```typescript
<PreferencesProvider>
  <ThemeProvider>
    ...
  </ThemeProvider>
</PreferencesProvider>
```

- [ ] **Step 3: Update ThemeProvider to read from preferences**

Modify ThemeProvider to accept an initial theme from preferences, falling back to localStorage:

```typescript
// In ThemeProvider, update initial state:
const { preferences } = usePreferences();
const initial = preferences.theme
  ? themes.find(t => t.id === preferences.theme) || themes[0]
  : /* existing localStorage logic */;
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/providers/PreferencesProvider.tsx frontend/src/App.tsx frontend/src/providers/ThemeProvider.tsx
git commit -m "feat: add PreferencesProvider, wire into App, update ThemeProvider"
```

---

## Phase 3: Dashboard UI

### Task 10: UserMenu molecule and TopBar update

**Files:**
- Create: `frontend/src/components/molecules/UserMenu.tsx`
- Modify: `frontend/src/components/organisms/TopBar.tsx`

- [ ] **Step 1: Create UserMenu**

```typescript
// UserMenu.tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar } from '../atoms/Avatar';
import { DropdownMenu } from '../atoms/DropdownMenu';
import { useAuth } from '../../hooks/useAuth';

export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="cursor-pointer">
        <Avatar src={user?.avatar_url} alt={user?.username} size={32} />
      </button>
      <DropdownMenu
        open={open}
        onClose={() => setOpen(false)}
        className="right-0 top-10 min-w-[140px]"
        items={[
          { label: 'Dashboard', onClick: () => navigate('/dashboard') },
          { label: 'Logout', onClick: logout },
        ]}
      />
    </div>
  );
}
```

- [ ] **Step 2: Update TopBar to use UserMenu**

Replace the username + logout button with `<UserMenu />`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/molecules/UserMenu.tsx frontend/src/components/organisms/TopBar.tsx
git commit -m "feat: add UserMenu dropdown, replace logout button in TopBar"
```

---

### Task 11: DashboardPage and DashboardNav

**Files:**
- Create: `frontend/src/pages/DashboardPage.tsx`
- Create: `frontend/src/components/organisms/DashboardNav.tsx`
- Modify: `frontend/src/App.tsx` (add route)

- [ ] **Step 1: Create DashboardNav**

```typescript
// DashboardNav.tsx
import { Icon } from '../atoms/Icon';

type Section = 'conversations' | 'profile' | 'keys' | 'connections';

interface DashboardNavProps {
  active: Section;
  onSelect: (section: Section) => void;
}

const NAV_ITEMS: { id: Section; label: string; icon: string }[] = [
  { id: 'conversations', label: 'Conversations', icon: 'chat' },
  { id: 'profile', label: 'Profile', icon: 'user' },
  { id: 'keys', label: 'API Keys', icon: 'key' },
  { id: 'connections', label: 'Connections', icon: 'link' },
];

export function DashboardNav({ active, onSelect }: DashboardNavProps) {
  return (
    <nav className="flex flex-col gap-1 p-3">
      <a href="/" className="text-sm text-[var(--accent)] hover:underline mb-4 px-3">
        ← Back to Chat
      </a>
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect(item.id)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer ${
            active === item.id
              ? 'bg-[var(--msg-user)] text-[var(--accent)] font-medium'
              : 'text-[var(--text)] hover:bg-[var(--msg-user)]'
          }`}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
```

Note: Add `chat`, `key`, and `link` icons to `Icon.tsx` if they don't exist.

- [ ] **Step 2: Create DashboardPage**

```typescript
// DashboardPage.tsx
import { useState } from 'react';
import { DashboardNav } from '../components/organisms/DashboardNav';
import { ConversationList } from '../components/organisms/ConversationList';
import { ProfilePanel } from '../components/organisms/ProfilePanel';
import { ApiKeyPanel } from '../components/organisms/ApiKeyPanel';
import { ConnectionsPanel } from '../components/organisms/ConnectionsPanel';
import { ParticleCanvas } from '../components/atoms/ParticleCanvas';
import { useTheme } from '../hooks/useTheme';

type Section = 'conversations' | 'profile' | 'keys' | 'connections';

export function DashboardPage() {
  const { theme } = useTheme();
  const [section, setSection] = useState<Section>('conversations');

  const panels: Record<Section, React.ReactNode> = {
    conversations: <ConversationList />,
    profile: <ProfilePanel />,
    keys: <ApiKeyPanel />,
    connections: <ConnectionsPanel />,
  };

  return (
    <div className="h-screen flex bg-[var(--bg-base)]">
      <ParticleCanvas theme={theme.id} />
      <div className="w-64 border-r border-[var(--accent)] backdrop-blur-md">
        <DashboardNav active={section} onSelect={setSection} />
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {panels[section]}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add route to App.tsx**

Inside the Routes, add:
```typescript
<Route path="/dashboard" element={<DashboardPage />} />
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/components/organisms/DashboardNav.tsx frontend/src/App.tsx
git commit -m "feat: add DashboardPage with left nav and routing"
```

---

### Task 12: ConversationList organism

**Files:**
- Create: `frontend/src/components/organisms/ConversationList.tsx`
- Create: `frontend/src/components/molecules/ConversationItem.tsx`

- [ ] **Step 1: Create ConversationItem**

```typescript
// ConversationItem.tsx
interface ConversationItemProps {
  title: string;
  date: string;
  folder: string | null;
  onClick: () => void;
  onDelete: () => void;
}

export function ConversationItem({ title, date, folder, onClick, onDelete }: ConversationItemProps) {
  return (
    <div
      onClick={onClick}
      className="flex items-center justify-between px-4 py-3 border-b border-[var(--glass-border)] hover:bg-[var(--msg-user)] cursor-pointer transition-colors"
    >
      <div className="flex-1 min-w-0">
        <div className="text-sm text-[var(--text)] font-medium truncate">{title}</div>
        <div className="text-xs text-[var(--text-muted)] mt-0.5">
          {new Date(date).toLocaleDateString()}
          {folder && <span className="ml-2 text-[var(--accent)]">#{folder}</span>}
        </div>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="text-xs text-[var(--text-muted)] hover:text-[var(--danger)] ml-2 cursor-pointer"
      >
        ✕
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Create ConversationList**

```typescript
// ConversationList.tsx
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ConversationItem } from '../molecules/ConversationItem';
import { listConversations, deleteConversation } from '../../api/conversations';
import type { Conversation } from '../../atoms/conversation';

export function ConversationList() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    const data = await listConversations({ q: search || undefined, page, limit: 20 });
    setConversations(data.conversations);
    setTotal(data.total);
  }, [search, page]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id: string) => {
    await deleteConversation(id);
    load();
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-[var(--text)] mb-4">Conversations</h2>
      <input
        type="text"
        placeholder="Search conversations..."
        value={search}
        onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        className="w-full bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2 text-sm font-mono outline-none focus:border-[var(--accent)] transition-all mb-4"
      />
      {conversations.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">No conversations yet.</p>
      ) : (
        <div className="border border-[var(--glass-border)] rounded-lg overflow-hidden">
          {conversations.map((c) => (
            <ConversationItem
              key={c.id}
              title={c.title}
              date={c.updated_at}
              folder={c.folder}
              onClick={() => navigate(`/?conversation=${c.id}`)}
              onDelete={() => handleDelete(c.id)}
            />
          ))}
        </div>
      )}
      {total > 20 && (
        <div className="flex justify-center gap-2 mt-4">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
            className="text-sm text-[var(--accent)] disabled:opacity-50 cursor-pointer">← Prev</button>
          <span className="text-sm text-[var(--text-muted)]">Page {page}</span>
          <button disabled={page * 20 >= total} onClick={() => setPage(p => p + 1)}
            className="text-sm text-[var(--accent)] disabled:opacity-50 cursor-pointer">Next →</button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/organisms/ConversationList.tsx frontend/src/components/molecules/ConversationItem.tsx
git commit -m "feat: add ConversationList and ConversationItem components"
```

---

### Task 13: ProfilePanel, ApiKeyPanel, ConnectionsPanel

**Files:**
- Create: `frontend/src/components/organisms/ProfilePanel.tsx`
- Create: `frontend/src/components/organisms/ApiKeyPanel.tsx`
- Create: `frontend/src/components/molecules/ApiKeyRow.tsx`
- Create: `frontend/src/components/molecules/CreateKeyModal.tsx`
- Create: `frontend/src/components/organisms/ConnectionsPanel.tsx`

- [ ] **Step 1: Create ProfilePanel (stub with edit)**

Displays username, email, avatar, auth method, role. Editable username and email. Password change for local auth users. Uses `updateProfile` and `changePassword` from `api/preferences.ts`.

- [ ] **Step 2: Create ApiKeyRow and CreateKeyModal**

ApiKeyRow shows prefix, label, dates, revoke button. CreateKeyModal prompts for label, shows raw key once with copy button.

- [ ] **Step 3: Create ApiKeyPanel**

Fetches keys from `GET /api/auth/keys`, renders table of ApiKeyRow, "Create Key" button opens CreateKeyModal, revoke calls `DELETE /api/auth/keys/<id>`.

- [ ] **Step 4: Create ConnectionsPanel (stub)**

```typescript
export function ConnectionsPanel() {
  return (
    <div>
      <h2 className="text-lg font-semibold text-[var(--text)] mb-4">Manage Connections</h2>
      <p className="text-sm text-[var(--text-muted)]">
        Anthropic, Cohere, Mistral, and more — coming soon.
      </p>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/organisms/ProfilePanel.tsx frontend/src/components/organisms/ApiKeyPanel.tsx frontend/src/components/molecules/ApiKeyRow.tsx frontend/src/components/molecules/CreateKeyModal.tsx frontend/src/components/organisms/ConnectionsPanel.tsx
git commit -m "feat: add ProfilePanel, ApiKeyPanel, and ConnectionsPanel"
```

---

## Phase 4: Chat Integration

### Task 14: ChatProvider conversation tracking

**Files:**
- Modify: `frontend/src/providers/ChatProvider.tsx`
- Modify: `frontend/src/api/chat.ts`

- [ ] **Step 1: Update streamChatAsync to accept conversation_id**

In `api/chat.ts`, add `conversationId` parameter:

```typescript
export function streamChatAsync(message: string, conversationId?: string | null) {
  const controller = new AbortController();
  const resp = fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal: controller.signal,
  });
  // ... rest unchanged
}
```

- [ ] **Step 2: Update ChatProvider**

Add `conversationId` state, `loadConversation`, `newConversation` methods. On stream `meta` event, capture `conversation_id`. Pass `conversationId` to `streamChatAsync`.

- [ ] **Step 3: Handle conversation loading from URL**

In ChatPage, read `?conversation=<id>` from URL params and call `loadConversation(id)`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/providers/ChatProvider.tsx frontend/src/api/chat.ts frontend/src/pages/ChatPage.tsx
git commit -m "feat: ChatProvider conversation tracking and persistence"
```

---

### Task 15: NewConversationButton and ConversationTitle

**Files:**
- Create: `frontend/src/components/molecules/NewConversationButton.tsx`
- Create: `frontend/src/components/molecules/ConversationTitle.tsx`
- Create: `frontend/src/components/molecules/SaveConversationModal.tsx`
- Modify: `frontend/src/components/organisms/MessageList.tsx`

- [ ] **Step 1: Create NewConversationButton**

Renders at top of chat area. Visible only when messages exist. In auto mode: clears chat. In prompt mode: opens SaveConversationModal. In never mode: clears chat.

- [ ] **Step 2: Create ConversationTitle**

Displays conversation title with pencil icon. Clicking pencil makes it editable inline. On blur or Enter, sends PATCH to update title.

- [ ] **Step 3: Create SaveConversationModal**

Uses Modal atom. Shows editable title (default: first 50 chars of first user message), folder dropdown, Save and Discard buttons.

- [ ] **Step 4: Wire into MessageList**

Add ConversationTitle above DateSeparator and NewConversationButton at top of chat area.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/molecules/NewConversationButton.tsx frontend/src/components/molecules/ConversationTitle.tsx frontend/src/components/molecules/SaveConversationModal.tsx frontend/src/components/organisms/MessageList.tsx
git commit -m "feat: add conversation UI (title, new conversation, save modal)"
```

---

### Task 16: Frontend build and integration test

**Files:**
- Modify: `frontend/` (build)

- [ ] **Step 1: Run frontend build**

```bash
cd frontend && npm run build
```

Fix any TypeScript errors.

- [ ] **Step 2: Restart server, test full flow**

1. Login → see avatar menu in top bar
2. Send a message → conversation auto-created
3. Click "New Conversation" → fresh chat
4. Navigate to Dashboard → see conversation list
5. Click conversation → loads in chat
6. Test profile edit, API key create/revoke
7. Test search in conversation list

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: user dashboard with conversation persistence, preferences, and API key management"
```
