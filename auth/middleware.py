"""Auth middleware: session/API key validation, route protection."""

import os
from datetime import datetime, timezone

import bcrypt
from flask import request, g, jsonify
from flask_login import LoginManager, current_user

from auth.models import User, UserSession, ApiKey
from auth.db import get_db

login_manager = LoginManager()

PUBLIC_PATHS = frozenset({
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/oauth/github",
    "/api/auth/oauth/github/callback",
    "/api/auth/oauth/google",
    "/api/auth/oauth/google/callback",
})

# Static IP auto-auth is disabled for now per user request.
# ADMIN_STATIC_IP = os.environ.get("ADMIN_STATIC_IP", "50.248.206.70")


@login_manager.user_loader
def load_user(user_id: str):
    db = get_db()
    return db.query(User).get(user_id)


@login_manager.request_loader
def load_user_from_request(req):
    """Try to authenticate via session cookie or API key header."""

    # 1. Session cookie
    session_id = req.cookies.get("session_id")
    if session_id:
        db = get_db()
        sess = db.query(UserSession).get(session_id)
        if sess and sess.expires_at > datetime.now(timezone.utc):
            return sess.user

    # 2. API key (Authorization: Bearer or X-API-Key)
    api_key = None
    auth_header = req.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]
    elif req.headers.get("X-API-Key"):
        api_key = req.headers["X-API-Key"]

    if api_key:
        db = get_db()
        # Check against all non-revoked keys — bcrypt compare
        keys = db.query(ApiKey).filter_by(revoked=False).filter(
            ApiKey.key_prefix == api_key[:8]
        ).all()
        for k in keys:
            if bcrypt.checkpw(api_key.encode(), k.key_hash.encode()):
                k.last_used = datetime.now(timezone.utc)
                db.commit()
                return k.user

    return None


def is_public_path(path: str) -> bool:
    """Check if a path is public (no auth required)."""
    if path in PUBLIC_PATHS:
        return True
    # SPA routes (non-API) are always public
    if not path.startswith("/api/"):
        return True
    return False


def auth_guard():
    """Before-request hook: block unauthenticated access to protected API routes."""
    if is_public_path(request.path):
        return None
    if current_user.is_authenticated:
        return None
    return jsonify({"error": "Authentication required"}), 401


def admin_required(f):
    """Decorator for admin-only routes."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated
