# tests/test_accounting_journal.py
"""Test journal entry, search, void, and account ledger tools."""
import json
import pytest


def test_journalize_basic(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl
    result = json.loads(_journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Owner investment",
        [
            {"account": "Cash", "debit": 10000.00, "credit": 0},
            {"account": "Owner's Capital", "debit": 0, "credit": 10000.00},
        ]
    ))
    assert result["status"] == "success"
    assert len(result["data"]["lines"]) == 2


def test_journalize_unbalanced(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl
    result = json.loads(_journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Bad entry",
        [
            {"account": "Cash", "debit": 500.00, "credit": 0},
            {"account": "Revenue", "debit": 0, "credit": 400.00},
        ]
    ))
    assert result["status"] == "error"
    assert "not balance" in result["error"].lower() or "equal" in result["error"].lower()


def test_journalize_bad_account(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl
    result = json.loads(_journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Bad account",
        [
            {"account": "Cash", "debit": 100.00, "credit": 0},
            {"account": "Nonexistent", "debit": 0, "credit": 100.00},
        ]
    ))
    assert result["status"] == "error"
    assert "not found" in result["error"].lower()


def test_journalize_both_sides_on_one_line(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl
    result = json.loads(_journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Both sides",
        [
            {"account": "Cash", "debit": 100.00, "credit": 100.00},
        ]
    ))
    assert result["status"] == "error"


def test_balance_after_journal(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl, _get_account_balance_impl
    _journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Owner investment",
        [
            {"account": "Cash", "debit": 5000.00, "credit": 0},
            {"account": "Owner's Capital", "debit": 0, "credit": 5000.00},
        ]
    )
    db_session.flush()
    result = json.loads(_get_account_balance_impl(db_session, "test-user-001", "Cash"))
    assert float(result["data"]["balance"]) == 5000.00


def test_search_journal(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl, _search_journal_impl
    _journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Office supplies purchase",
        [
            {"account": "Supplies Expense", "debit": 75.00, "credit": 0},
            {"account": "Cash", "debit": 0, "credit": 75.00},
        ]
    )
    db_session.flush()
    result = json.loads(_search_journal_impl(db_session, "test-user-001", memo_text="supplies"))
    assert result["status"] == "success"
    assert len(result["data"]["entries"]) == 1


def test_void_transaction(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl, _void_transaction_impl, _get_account_balance_impl
    jr = json.loads(_journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Mistake",
        [
            {"account": "Cash", "debit": 200.00, "credit": 0},
            {"account": "Revenue", "debit": 0, "credit": 200.00},
        ]
    ))
    db_session.flush()
    entry_id = jr["data"]["journal_entry_id"]

    void = json.loads(_void_transaction_impl(
        db_session, "test-user-001", entry_id, "2026-03-20", "Voiding mistake"
    ))
    db_session.flush()
    assert void["status"] == "success"

    bal = json.loads(_get_account_balance_impl(db_session, "test-user-001", "Cash"))
    assert float(bal["data"]["balance"]) == 0.0


def test_void_already_voided(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl, _void_transaction_impl
    jr = json.loads(_journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "To void",
        [
            {"account": "Cash", "debit": 100.00, "credit": 0},
            {"account": "Revenue", "debit": 0, "credit": 100.00},
        ]
    ))
    db_session.flush()
    entry_id = jr["data"]["journal_entry_id"]

    _void_transaction_impl(db_session, "test-user-001", entry_id, "2026-03-20", "Void 1")
    db_session.flush()
    result = json.loads(_void_transaction_impl(db_session, "test-user-001", entry_id, "2026-03-20", "Void 2"))
    assert result["status"] == "error"
    assert "already voided" in result["error"].lower()


def test_void_a_void(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl, _void_transaction_impl
    jr = json.loads(_journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Original",
        [
            {"account": "Cash", "debit": 100.00, "credit": 0},
            {"account": "Revenue", "debit": 0, "credit": 100.00},
        ]
    ))
    db_session.flush()
    void = json.loads(_void_transaction_impl(
        db_session, "test-user-001", jr["data"]["journal_entry_id"], "2026-03-20", "Void"
    ))
    db_session.flush()
    result = json.loads(_void_transaction_impl(
        db_session, "test-user-001", void["data"]["reversal_entry_id"], "2026-03-20", "Void the void"
    ))
    assert result["status"] == "error"
    assert "reversal" in result["error"].lower() or "void" in result["error"].lower()


def test_account_ledger(db_session, ledger_with_defaults):
    from tools.accounting import _journalize_transaction_impl, _account_ledger_impl
    _journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-20", "Entry 1",
        [
            {"account": "Cash", "debit": 1000.00, "credit": 0},
            {"account": "Owner's Capital", "debit": 0, "credit": 1000.00},
        ]
    )
    _journalize_transaction_impl(
        db_session, "test-user-001", "2026-03-21", "Entry 2",
        [
            {"account": "Rent Expense", "debit": 500.00, "credit": 0},
            {"account": "Cash", "debit": 0, "credit": 500.00},
        ]
    )
    db_session.flush()
    result = json.loads(_account_ledger_impl(db_session, "test-user-001", "Cash"))
    assert result["status"] == "success"
    assert len(result["data"]["entries"]) == 2
    assert result["data"]["running_balance"] == "500.00"
