"""Flask routes for the accounting journal UI.

Thin wrappers around the _impl functions in tools/accounting.py.
Each route: get db session, call _impl, parse the JSON string result,
return it as a proper Flask JSON response.
"""
import json
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from auth.db import SessionLocal

acct_bp = Blueprint("accounting", __name__, url_prefix="/api/accounting")


def _db():
    return SessionLocal()


@acct_bp.route("/accounts", methods=["GET"])
@login_required
def accounts():
    from tools.accounting import _list_accounts_impl
    db = _db()
    try:
        result = json.loads(_list_accounts_impl(db, current_user.id))
        return jsonify(result)
    finally:
        db.close()


@acct_bp.route("/ledger", methods=["POST"])
@login_required
def create_ledger():
    from tools.accounting import _create_ledger_impl
    data = request.get_json(force=True)
    name = data.get("name", "My Ledger")
    db = _db()
    try:
        result = json.loads(_create_ledger_impl(db, current_user.id, name))
        if result.get("status") == "success":
            db.commit()
        else:
            db.rollback()
        return jsonify(result)
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "data": None, "error": str(e)}), 500
    finally:
        db.close()


@acct_bp.route("/journal", methods=["POST"])
@login_required
def post_journal():
    from tools.accounting import _journalize_transaction_impl
    data = request.get_json(force=True)
    date_str = data.get("date", "")
    memo = data.get("memo", "")
    lines = data.get("lines", [])
    db = _db()
    try:
        result = json.loads(_journalize_transaction_impl(db, current_user.id, date_str, memo, lines))
        if result.get("status") == "success":
            db.commit()
        else:
            db.rollback()
        return jsonify(result)
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "data": None, "error": str(e)}), 500
    finally:
        db.close()


@acct_bp.route("/trial-balance", methods=["GET"])
@login_required
def trial_balance():
    from tools.accounting import _trial_balance_impl
    as_of_date = request.args.get("as_of_date")
    db = _db()
    try:
        result = json.loads(_trial_balance_impl(db, current_user.id, as_of_date))
        return jsonify(result)
    finally:
        db.close()
