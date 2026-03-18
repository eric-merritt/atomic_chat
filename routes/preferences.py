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
