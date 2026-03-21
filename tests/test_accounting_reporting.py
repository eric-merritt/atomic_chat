# tests/test_accounting_reporting.py
"""Test period close and financial reporting tools."""
import json
import pytest


@pytest.fixture
def active_ledger(db_session, ledger_with_defaults):
    """Ledger with several transactions for reporting."""
    from tools.accounting import _journalize_transaction_impl
    # Owner investment
    _journalize_transaction_impl(db_session, "test-user-001", "2026-03-01", "Owner investment",
        [{"account": "Cash", "debit": 10000.00, "credit": 0},
         {"account": "Owner's Capital", "debit": 0, "credit": 10000.00}])
    # Revenue
    _journalize_transaction_impl(db_session, "test-user-001", "2026-03-15", "Service revenue",
        [{"account": "Cash", "debit": 3000.00, "credit": 0},
         {"account": "Revenue", "debit": 0, "credit": 3000.00}])
    # Expense
    _journalize_transaction_impl(db_session, "test-user-001", "2026-03-20", "Pay rent",
        [{"account": "Rent Expense", "debit": 1000.00, "credit": 0},
         {"account": "Cash", "debit": 0, "credit": 1000.00}])
    db_session.flush()
    return db_session


def test_trial_balance(active_ledger):
    from tools.accounting import _trial_balance_impl
    result = json.loads(_trial_balance_impl(active_ledger, "test-user-001"))
    assert result["status"] == "success"
    assert result["data"]["total_debits"] == result["data"]["total_credits"]


def test_income_statement(active_ledger):
    from tools.accounting import _income_statement_impl
    result = json.loads(_income_statement_impl(
        active_ledger, "test-user-001", "2026-03-01", "2026-03-31"
    ))
    assert result["status"] == "success"
    assert float(result["data"]["total_revenue"]) == 3000.00
    assert float(result["data"]["total_expenses"]) == 1000.00
    assert float(result["data"]["net_income"]) == 2000.00


def test_balance_sheet(active_ledger):
    from tools.accounting import _balance_sheet_impl
    result = json.loads(_balance_sheet_impl(active_ledger, "test-user-001"))
    assert result["status"] == "success"
    # A = L + E should hold
    assets = float(result["data"]["total_assets"])
    liabilities = float(result["data"]["total_liabilities"])
    equity = float(result["data"]["total_equity"])
    # Equity includes capital + unclosed revenue - unclosed expense
    assert abs(assets - (liabilities + equity)) < 0.01


def test_close_period(active_ledger):
    from tools.accounting import _close_period_impl, _get_account_balance_impl
    result = json.loads(_close_period_impl(active_ledger, "test-user-001", "2026-03-31"))
    active_ledger.flush()
    assert result["status"] == "success"
    assert float(result["data"]["net_income"]) == 2000.00

    # Revenue and expense should be zero after close
    rev = json.loads(_get_account_balance_impl(active_ledger, "test-user-001", "Revenue"))
    assert float(rev["data"]["balance"]) == 0.0
    exp = json.loads(_get_account_balance_impl(active_ledger, "test-user-001", "Rent Expense"))
    assert float(exp["data"]["balance"]) == 0.0

    # Capital should have increased by net income
    cap = json.loads(_get_account_balance_impl(active_ledger, "test-user-001", "Owner's Capital"))
    assert float(cap["data"]["balance"]) == 12000.00  # 10000 + 2000 net income


def test_close_period_zero_balances(db_session, ledger_with_defaults):
    """No revenue or expense → nothing to close."""
    from tools.accounting import _close_period_impl
    result = json.loads(_close_period_impl(db_session, "test-user-001", "2026-03-31"))
    assert result["status"] == "success"
    assert "nothing to close" in result["data"]["message"].lower()


def test_cash_flow_statement(active_ledger):
    from tools.accounting import _cash_flow_statement_impl
    result = json.loads(_cash_flow_statement_impl(
        active_ledger, "test-user-001", "2026-03-01", "2026-03-31"
    ))
    assert result["status"] == "success"
    # Net change in cash = +10000 (investment) + 3000 (revenue) - 1000 (rent) = 12000
    assert float(result["data"]["ending_cash"]) == 12000.00
