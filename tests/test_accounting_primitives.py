# tests/test_accounting_primitives.py
"""Test the internal _debit/_credit primitives and helpers."""
from decimal import Decimal
import json
import pytest
from auth.accounting_models import AccountType, JournalLine


def test_get_ledger_not_found(db_session):
    from tools.accounting import _get_ledger
    result = _get_ledger(db_session, "nonexistent-user")
    assert result is None


def test_get_ledger_found(db_session, ledger_with_defaults):
    from tools.accounting import _get_ledger
    result = _get_ledger(db_session, "test-user-001")
    assert result is not None
    assert result.name == "Test Ledger"


def test_resolve_account(db_session, ledger_with_defaults):
    from tools.accounting import _resolve_account
    acct = _resolve_account(db_session, ledger_with_defaults.id, "Cash")
    assert acct is not None
    assert acct.account_type == AccountType.ASSET


def test_resolve_account_not_found(db_session, ledger_with_defaults):
    from tools.accounting import _resolve_account
    acct = _resolve_account(db_session, ledger_with_defaults.id, "Nonexistent")
    assert acct is None


def test_create_default_accounts(db_session, ledger_with_defaults):
    from auth.accounting_models import Account
    accounts = db_session.query(Account).filter_by(ledger_id=ledger_with_defaults.id).all()
    names = {a.name for a in accounts}
    assert "Cash" in names
    assert "Accounts Receivable" in names
    assert "Inventory" in names
    assert "Accounts Payable" in names
    assert "Owner's Capital" in names
    assert "Income Summary" in names
    assert "Revenue" in names
    assert "Cost of Goods Sold" in names
