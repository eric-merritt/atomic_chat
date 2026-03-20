# tests/test_accounting_models.py
"""Test that accounting models are importable and have correct structure."""

def test_models_importable():
    from auth.accounting_models import (
        Ledger, Account, JournalEntry, JournalLine,
        InventoryItem, InventoryLayer,
        AccountType, NormalBalance, ItemType, SourceType,
    )
    assert Ledger.__tablename__ == "ledgers"
    assert Account.__tablename__ == "accounts"
    assert JournalEntry.__tablename__ == "journal_entries"
    assert JournalLine.__tablename__ == "journal_lines"
    assert InventoryItem.__tablename__ == "inventory_items"
    assert InventoryLayer.__tablename__ == "inventory_layers"

def test_account_type_enum():
    from auth.accounting_models import AccountType
    assert AccountType.ASSET.value == "asset"
    assert AccountType.LIABILITY.value == "liability"
    assert AccountType.EQUITY.value == "equity"
    assert AccountType.REVENUE.value == "revenue"
    assert AccountType.EXPENSE.value == "expense"

def test_normal_balance_derivation():
    from auth.accounting_models import AccountType, NORMAL_BALANCE_MAP, NormalBalance
    assert NORMAL_BALANCE_MAP[AccountType.ASSET] == NormalBalance.DEBIT
    assert NORMAL_BALANCE_MAP[AccountType.LIABILITY] == NormalBalance.CREDIT
    assert NORMAL_BALANCE_MAP[AccountType.EQUITY] == NormalBalance.CREDIT
    assert NORMAL_BALANCE_MAP[AccountType.REVENUE] == NormalBalance.CREDIT
    assert NORMAL_BALANCE_MAP[AccountType.EXPENSE] == NormalBalance.DEBIT

def test_source_type_enum():
    from auth.accounting_models import SourceType
    assert SourceType.MANUAL.value == "manual"
    assert SourceType.FIFO_SALE.value == "fifo_sale"
    assert SourceType.VOID.value == "void"
