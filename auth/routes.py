"""Auth blueprint: register, login, logout, me, API key management, OAuth."""

import os
import uuid
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, request, jsonify, g, redirect, url_for, current_app
from flask_login import login_user, logout_user, login_required, current_user

from auth.models import User, UserSession, ApiKey, OAuthToken
from auth.db import get_db

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

SESSION_LIFETIME = timedelta(hours=24)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()


def _check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _create_session(user: User) -> UserSession:
    db = get_db()
    session = UserSession(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + SESSION_LIFETIME,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:512],
    )
    db.add(session)
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    return session


def _user_json(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "auth_method": user.auth_method,
    }


# ── Register ─────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip() or None
    password = data.get("password") or ""

    if not username or len(username) < 3 or len(username) > 64:
        return jsonify({"error": "Username must be 3-64 characters"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    db = get_db()

    if db.query(User).filter_by(username=username).first():
        return jsonify({"error": "Username already taken"}), 409
    if email and db.query(User).filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        username=username,
        email=email,
        password_hash=_hash_password(password),
        auth_method="local",
        role="user",
    )
    db.add(user)
    db.commit()

    session = _create_session(user)
    login_user(user)

    resp = jsonify({"user": _user_json(user)})
    resp.status_code = 201
    resp.set_cookie(
        "session_id", session.id,
        httponly=True, samesite="Lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return resp


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    db = get_db()
    user = (
        db.query(User)
        .filter((User.username == username) | (User.email == username))
        .first()
    )

    if not user or not user.password_hash or not _check_password(password, user.password_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    session = _create_session(user)
    login_user(user)

    resp = jsonify({"user": _user_json(user)})
    resp.set_cookie(
        "session_id", session.id,
        httponly=True, samesite="Lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return resp


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session_id = request.cookies.get("session_id")
    if session_id:
        db = get_db()
        sess = db.query(UserSession).get(session_id)
        if sess:
            db.delete(sess)
            db.commit()

    logout_user()
    resp = jsonify({"ok": True})
    resp.delete_cookie("session_id")
    return resp


# ── Current user ──────────────────────────────────────────────────────────────

@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return jsonify({"user": _user_json(current_user)})


# ── API Key Management ────────────────────────────────────────────────────────

@auth_bp.route("/keys", methods=["GET"])
@login_required
def list_keys():
    db = get_db()
    keys = db.query(ApiKey).filter_by(user_id=current_user.id, revoked=False).all()
    return jsonify({"keys": [
        {
            "id": k.id,
            "prefix": k.key_prefix,
            "label": k.label,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used": k.last_used.isoformat() if k.last_used else None,
        }
        for k in keys
    ]})


@auth_bp.route("/keys", methods=["POST"])
@login_required
def create_key():
    data = request.get_json(force=True)
    label = (data.get("label") or "").strip() or "Untitled"

    raw_key = f"ak_{secrets.token_urlsafe(32)}"
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt(12)).decode()

    db = get_db()
    api_key = ApiKey(
        user_id=current_user.id,
        key_hash=key_hash,
        key_prefix=raw_key[:8],
        label=label,
    )
    db.add(api_key)
    db.commit()

    return jsonify({
        "key": raw_key,
        "id": api_key.id,
        "prefix": api_key.key_prefix,
        "label": api_key.label,
        "warning": "Store this key securely — it cannot be shown again.",
    }), 201


@auth_bp.route("/keys/<key_id>", methods=["DELETE"])
@login_required
def revoke_key(key_id):
    db = get_db()
    api_key = db.query(ApiKey).filter_by(id=key_id, user_id=current_user.id).first()
    if not api_key:
        return jsonify({"error": "Key not found"}), 404
    api_key.revoked = True
    db.commit()
    return jsonify({"ok": True})


# ── OAuth Setup ──────────────────────────────────────────────────────────────

oauth = OAuth()

OAUTH_REDIRECT_BASE = os.environ.get("OAUTH_REDIRECT_BASE", "http://localhost:5000")


def init_oauth(app):
    """Register OAuth providers with the Flask app. Call from main.py."""
    oauth.init_app(app)

    github_id = os.environ.get("GITHUB_CLIENT_ID")
    github_secret = os.environ.get("GITHUB_CLIENT_SECRET")
    if github_id and github_secret:
        oauth.register(
            name="github",
            client_id=github_id,
            client_secret=github_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "user:email"},
        )

    google_id = os.environ.get("GOOGLE_CLIENT_ID")
    google_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if google_id and google_secret:
        oauth.register(
            name="google",
            client_id=google_id,
            client_secret=google_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )


def _find_or_create_oauth_user(provider: str, provider_id: str, email: str | None,
                                username: str, avatar_url: str | None) -> User:
    """Look up an existing OAuth user or create a new one."""
    db = get_db()
    user = db.query(User).filter_by(oauth_provider=provider, oauth_provider_id=provider_id).first()
    if user:
        user.last_login = datetime.now(timezone.utc)
        if avatar_url:
            user.avatar_url = avatar_url
        db.commit()
        return user

    # Check if email matches an existing local user — link accounts
    if email:
        user = db.query(User).filter_by(email=email).first()
        if user:
            user.oauth_provider = provider
            user.oauth_provider_id = provider_id
            user.auth_method = "oauth"
            user.last_login = datetime.now(timezone.utc)
            if avatar_url:
                user.avatar_url = avatar_url
            db.commit()
            return user

    # Ensure unique username
    base = username or provider_id
    candidate = base
    n = 1
    while db.query(User).filter_by(username=candidate).first():
        candidate = f"{base}_{n}"
        n += 1

    user = User(
        username=candidate,
        email=email,
        auth_method="oauth",
        oauth_provider=provider,
        oauth_provider_id=provider_id,
        role="user",
        avatar_url=avatar_url,
    )
    db.add(user)
    db.commit()
    return user


def _store_oauth_token(user: User, provider: str, token: dict):
    """Persist or update the OAuth token for a user+provider pair."""
    db = get_db()
    existing = db.query(OAuthToken).filter_by(user_id=user.id, provider=provider).first()
    if existing:
        existing.access_token = token.get("access_token")
        existing.refresh_token = token.get("refresh_token")
        existing.scopes = token.get("scope", "")
    else:
        db.add(OAuthToken(
            user_id=user.id,
            provider=provider,
            access_token=token.get("access_token"),
            refresh_token=token.get("refresh_token"),
            scopes=token.get("scope", ""),
        ))
    db.commit()


# ── GitHub OAuth ─────────────────────────────────────────────────────────────

@auth_bp.route("/oauth/github")
def oauth_github():
    if "github" not in oauth._clients:
        return jsonify({"error": "GitHub OAuth not configured"}), 501
    redirect_uri = f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/github/callback"
    return oauth.github.authorize_redirect(redirect_uri)


@auth_bp.route("/oauth/github/callback")
def oauth_github_callback():
    if "github" not in oauth._clients:
        return jsonify({"error": "GitHub OAuth not configured"}), 501

    token = oauth.github.authorize_access_token()
    resp = oauth.github.get("user", token=token)
    profile = resp.json()

    # Fetch primary email if not public
    email = profile.get("email")
    if not email:
        emails_resp = oauth.github.get("user/emails", token=token)
        for e in emails_resp.json():
            if e.get("primary") and e.get("verified"):
                email = e["email"]
                break

    user = _find_or_create_oauth_user(
        provider="github",
        provider_id=str(profile["id"]),
        email=email,
        username=profile.get("login", ""),
        avatar_url=profile.get("avatar_url"),
    )
    _store_oauth_token(user, "github", token)

    session = _create_session(user)
    login_user(user)

    resp = redirect("/")
    resp.set_cookie(
        "session_id", session.id,
        httponly=True, samesite="Lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return resp


# ── Google OAuth ─────────────────────────────────────────────────────────────

@auth_bp.route("/oauth/google")
def oauth_google():
    if "google" not in oauth._clients:
        return jsonify({"error": "Google OAuth not configured"}), 501
    redirect_uri = f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/google/callback"
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/oauth/google/callback")
def oauth_google_callback():
    if "google" not in oauth._clients:
        return jsonify({"error": "Google OAuth not configured"}), 501

    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo")
    if not userinfo:
        resp = oauth.google.get("https://openidconnect.googleapis.com/v1/userinfo", token=token)
        userinfo = resp.json()

    user = _find_or_create_oauth_user(
        provider="google",
        provider_id=userinfo["sub"],
        email=userinfo.get("email"),
        username=userinfo.get("name", "").replace(" ", "_").lower(),
        avatar_url=userinfo.get("picture"),
    )
    _store_oauth_token(user, "google", token)

    session = _create_session(user)
    login_user(user)

    resp = redirect("/")
    resp.set_cookie(
        "session_id", session.id,
        httponly=True, samesite="Lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return resp
