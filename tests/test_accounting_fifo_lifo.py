# tests/test_accounting_fifo_lifo.py
"""Test FIFO/LIFO inventory costing and valuation."""
import json
import pytest


@pytest.fixture
def stocked_ledger(db_session, ledger_with_defaults):
    """Ledger with 2 inventory layers at different costs."""
    from tools.accounting import (
        _register_inventory_item_impl, _receive_inventory_impl, _journalize_transaction_impl,
    )
    # Seed cash
    _journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-01", "Owner investment",
        [{"account": "Cash", "debit": 50000.00, "credit": 0},
         {"account": "Owner's Capital", "debit": 0, "credit": 50000.00}]
    )
    _register_inventory_item_impl(db_session, "test-user-001", "GPU-001", "RTX 3060", "goods", 300.00)
    db_session.flush()
    # Layer 1: 10 units @ $200 (oldest)
    _receive_inventory_impl(db_session, "test-user-001", "GPU-001", 10, 200.00, "2026-03-05", "Cash")
    db_session.flush()
    # Layer 2: 10 units @ $250 (newest)
    _receive_inventory_impl(db_session, "test-user-001", "GPU-001", 10, 250.00, "2026-03-10", "Cash")
    db_session.flush()
    return db_session


def test_fifo_sale(stocked_ledger):
    from tools.accounting import _journalize_fifo_transaction_impl, _get_account_balance_impl
    result = json.loads(_journalize_fifo_transaction_impl(
        stocked_ledger, "test-user-001", "2026-03-20", "Sold 5 GPUs",
        "GPU-001", 5, 300.00
    ))
    stocked_ledger.flush()
    assert result["status"] == "success"
    # FIFO: 5 units from Layer 1 @ $200 = $1000 COGS
    assert float(result["data"]["total_cogs"]) == 1000.00
    assert float(result["data"]["sale_total"]) == 1500.00  # 5 * $300


def test_lifo_sale(stocked_ledger):
    from tools.accounting import _journalize_lifo_transaction_impl
    result = json.loads(_journalize_lifo_transaction_impl(
        stocked_ledger, "test-user-001", "2026-03-20", "Sold 5 GPUs LIFO",
        "GPU-001", 5, 300.00
    ))
    stocked_ledger.flush()
    assert result["status"] == "success"
    # LIFO: 5 units from Layer 2 @ $250 = $1250 COGS
    assert float(result["data"]["total_cogs"]) == 1250.00


def test_fifo_insufficient_inventory(stocked_ledger):
    from tools.accounting import _journalize_fifo_transaction_impl
    result = json.loads(_journalize_fifo_transaction_impl(
        stocked_ledger, "test-user-001", "2026-03-20", "Too many",
        "GPU-001", 25, 300.00  # only 20 in stock
    ))
    assert result["status"] == "error"
    assert "insufficient" in result["error"].lower()


def test_fifo_rejects_service_items(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl, _journalize_fifo_transaction_impl
    _register_inventory_item_impl(db_session, "test-user-001", "SVC-001", "Consulting", "service")
    db_session.flush()
    result = json.loads(_journalize_fifo_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Bad",
        "SVC-001", 1, 100.00
    ))
    assert result["status"] == "error"
    assert "service" in result["error"].lower()


def test_fifo_multi_layer_consumption(stocked_ledger):
    """Sell 15 units — should consume all of Layer 1 (10@$200) + 5 from Layer 2 (5@$250)."""
    from tools.accounting import _journalize_fifo_transaction_impl
    result = json.loads(_journalize_fifo_transaction_impl(
        stocked_ledger, "test-user-001", "2026-03-20", "Big sale",
        "GPU-001", 15, 300.00
    ))
    stocked_ledger.flush()
    assert result["status"] == "success"
    # COGS: (10 * 200) + (5 * 250) = 2000 + 1250 = 3250
    assert float(result["data"]["total_cogs"]) == 3250.00
    assert len(result["data"]["layers_consumed"]) == 2


def test_inventory_valuation_fifo(stocked_ledger):
    from tools.accounting import _inventory_valuation_impl
    result = json.loads(_inventory_valuation_impl(stocked_ledger, "test-user-001", "fifo"))
    assert result["status"] == "success"
    items = result["data"]["items"]
    assert len(items) == 1
    # 20 units: (10 * 200) + (10 * 250) = 4500
    assert float(items[0]["total_cost"]) == 4500.00
    assert float(items[0]["quantity_on_hand"]) == 20
