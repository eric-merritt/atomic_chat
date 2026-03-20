# tests/test_accounting_ledger.py
"""Test ledger setup and account management tools."""
import json
import pytest
from auth.models import User


def test_create_ledger(db_session):
    from tools.accounting import _create_ledger_impl
    # Must create user first (FK constraint)
    user = User(id="test-user-new", username="newuser", auth_method="local")
    db_session.add(user)
    db_session.flush()
    result = json.loads(_create_ledger_impl(db_session, "test-user-new", "My Business"))
    assert result["status"] == "success"
    assert result["data"]["name"] == "My Business"
    assert len(result["data"]["accounts_created"]) == 12  # default accounts


def test_create_ledger_duplicate(db_session, ledger_with_defaults):
    from tools.accounting import _create_ledger_impl
    result = json.loads(_create_ledger_impl(db_session, "test-user-001", "Dup"))
    assert result["status"] == "error"
    assert "already has a ledger" in result["error"]


def test_create_account(db_session, ledger_with_defaults):
    from tools.accounting import _create_account_impl
    result = json.loads(_create_account_impl(
        db_session, "test-user-001", "Office Equipment", "asset", "1500"
    ))
    assert result["status"] == "success"
    assert result["data"]["name"] == "Office Equipment"
    assert result["data"]["account_type"] == "asset"
    assert result["data"]["normal_balance"] == "debit"


def test_create_account_duplicate_name(db_session, ledger_with_defaults):
    from tools.accounting import _create_account_impl
    result = json.loads(_create_account_impl(
        db_session, "test-user-001", "Cash", "asset"
    ))
    assert result["status"] == "error"
    assert "already exists" in result["error"]


def test_list_accounts(db_session, ledger_with_defaults):
    from tools.accounting import _list_accounts_impl
    result = json.loads(_list_accounts_impl(db_session, "test-user-001"))
    assert result["status"] == "success"
    assert len(result["data"]["accounts"]) == 12


def test_list_accounts_filtered(db_session, ledger_with_defaults):
    from tools.accounting import _list_accounts_impl
    result = json.loads(_list_accounts_impl(db_session, "test-user-001", "asset"))
    assert result["status"] == "success"
    names = {a["name"] for a in result["data"]["accounts"]}
    assert "Cash" in names
    assert "Revenue" not in names


def test_get_account_balance_zero(db_session, ledger_with_defaults):
    from tools.accounting import _get_account_balance_impl
    result = json.loads(_get_account_balance_impl(db_session, "test-user-001", "Cash"))
    assert result["status"] == "success"
    assert float(result["data"]["balance"]) == 0.0


def test_update_account_rename(db_session, ledger_with_defaults):
    from tools.accounting import _update_account_impl
    result = json.loads(_update_account_impl(
        db_session, "test-user-001", "Rent Expense", new_name="Office Rent Expense"
    ))
    assert result["status"] == "success"
    assert result["data"]["name"] == "Office Rent Expense"


def test_update_account_deactivate(db_session, ledger_with_defaults):
    from tools.accounting import _update_account_impl
    result = json.loads(_update_account_impl(
        db_session, "test-user-001", "Supplies Expense", is_active=False
    ))
    assert result["status"] == "success"
    assert result["data"]["is_active"] is False
