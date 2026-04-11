"""Tool selection endpoints."""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from auth.db import get_db
from pipeline.workflow_groups import WORKFLOW_GROUPS

tools_bp = Blueprint("tools", __name__, url_prefix="/api")


@tools_bp.route("/tools/select-group", methods=["POST"])
@login_required
def select_group():
    data = request.get_json(force=True)
    group_name = data.get("group", "")
    active = data.get("active", True)

    wg = WORKFLOW_GROUPS.get(group_name)
    if not wg:
        return jsonify({"error": f"Unknown group: {group_name}"}), 404

    db = get_db()
    prefs = dict(current_user.preferences or {})
    selected = set(prefs.get("selected_tools", []))

    if active:
        selected.update(wg.tools)
    else:
        selected -= set(wg.tools)

    prefs["selected_tools"] = sorted(selected)
    current_user.preferences = prefs
    db.commit()

    return jsonify({"ok": True, "selected": prefs["selected_tools"]})
