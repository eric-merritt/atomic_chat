# tests/test_accounting_inventory.py
"""Test inventory registration, receiving, and listing."""
import json
import pytest


def _load(result):
    return result if isinstance(result, dict) else json.loads(result)


def test_register_item(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl
    result = _load(_register_inventory_item_impl(
        db_session, "test-user-001", "WDG-001", "Widget", "goods", 29.99
    ))
    assert result["status"] == "success"
    assert result["data"]["sku"] == "WDG-001"


def test_register_duplicate_sku(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl
    _register_inventory_item_impl(db_session, "test-user-001", "WDG-001", "Widget", "goods")
    db_session.flush()
    result = _load(_register_inventory_item_impl(
        db_session, "test-user-001", "WDG-001", "Duplicate", "goods"
    ))
    assert result["status"] == "error"
    assert "already exists" in result["error"].lower()


def test_receive_inventory(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl, _receive_inventory_impl, _get_account_balance_impl
    _register_inventory_item_impl(db_session, "test-user-001", "WDG-001", "Widget", "goods")
    db_session.flush()

    result = _load(_receive_inventory_impl(
        db_session, "test-user-001", "WDG-001", 100, 5.00, "2026-03-20", "Cash"
    ))
    assert result["status"] == "success"
    assert result["data"]["layer"]["quantity_purchased"] == "100"
    assert result["data"]["journal_entry_id"] is not None

    # Verify accounting: Inventory debited, Cash credited
    inv_bal = _load(_get_account_balance_impl(db_session, "test-user-001", "Inventory"))
    cash_bal = _load(_get_account_balance_impl(db_session, "test-user-001", "Cash"))
    assert float(inv_bal["data"]["balance"]) == 500.00
    assert float(cash_bal["data"]["balance"]) == -500.00


def test_list_inventory(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl, _receive_inventory_impl, _list_inventory_items_impl
    _register_inventory_item_impl(db_session, "test-user-001", "WDG-001", "Widget", "goods")
    db_session.flush()
    _receive_inventory_impl(db_session, "test-user-001", "WDG-001", 50, 5.00, "2026-03-20", "Cash")
    db_session.flush()

    result = _load(_list_inventory_items_impl(db_session, "test-user-001"))
    assert result["status"] == "success"
    assert len(result["data"]["items"]) == 1
    assert float(result["data"]["items"][0]["quantity_on_hand"]) == 50


def test_deactivate_inventory_item(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl, _deactivate_inventory_item_impl
    _register_inventory_item_impl(db_session, "test-user-001", "SVC-001", "Consulting", "service")
    db_session.flush()

    result = _load(_deactivate_inventory_item_impl(db_session, "test-user-001", "SVC-001"))
    assert result["status"] == "success"
    assert result["data"]["is_active"] is False


def test_deactivate_with_remaining_inventory(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl, _receive_inventory_impl, _deactivate_inventory_item_impl
    _register_inventory_item_impl(db_session, "test-user-001", "WDG-001", "Widget", "goods")
    db_session.flush()
    _receive_inventory_impl(db_session, "test-user-001", "WDG-001", 10, 5.00, "2026-03-20", "Cash")
    db_session.flush()

    result = _load(_deactivate_inventory_item_impl(db_session, "test-user-001", "WDG-001"))
    assert result["status"] == "error"
    assert "quantity_remaining" in result["error"].lower() or "deplete" in result["error"].lower()
