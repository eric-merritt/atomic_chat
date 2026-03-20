# tools/accounting.py
"""Accounting tools: double-entry bookkeeping, inventory, reporting.

21 LLM-facing tools backed by PostgreSQL.
Uses standardized output: {"status": "success"|"error", "data": ..., "error": ""}
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy.orm import Session

from auth.accounting_models import (
    Ledger, Account, JournalEntry, JournalLine,
    InventoryItem, InventoryLayer,
    AccountType, NormalBalance, ItemType, SourceType,
    NORMAL_BALANCE_MAP,
)
from auth.db import SessionLocal
from tools._output import tool_result


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_db() -> Session:
    """Get a database session."""
    return SessionLocal()


def _get_ledger(db: Session, user_id: str) -> Optional[Ledger]:
    """Get the ledger for a user, or None."""
    return db.query(Ledger).filter_by(user_id=user_id).first()


def _resolve_account(db: Session, ledger_id: int, name: str) -> Optional[Account]:
    """Look up an active account by name within a ledger."""
    return db.query(Account).filter_by(
        ledger_id=ledger_id, name=name, is_active=True
    ).first()


def _parse_date(date_str: str) -> date:
    """Parse YYYY-MM-DD string to date. Raises ValueError on bad format."""
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _parse_amount(amount) -> Decimal:
    """Parse a number to Decimal. Raises ValueError if invalid or non-positive."""
    d = Decimal(str(amount))
    if d <= 0:
        raise ValueError(f"Amount must be positive, got {d}")
    return d


# ── Default Accounts ─────────────────────────────────────────────────────────

DEFAULT_ACCOUNTS = [
    # (name, type)
    ("Cash", AccountType.ASSET),
    ("Accounts Receivable", AccountType.ASSET),
    ("Inventory", AccountType.ASSET),
    ("Accounts Payable", AccountType.LIABILITY),
    ("Owner's Capital", AccountType.EQUITY),
    ("Income Summary", AccountType.EQUITY),
    ("Revenue", AccountType.REVENUE),
    ("Cost of Goods Sold", AccountType.EXPENSE),
    ("Rent Expense", AccountType.EXPENSE),
    ("Utilities Expense", AccountType.EXPENSE),
    ("Supplies Expense", AccountType.EXPENSE),
    ("Wages Expense", AccountType.EXPENSE),
]


def _create_default_accounts(db: Session, ledger_id: int) -> list[Account]:
    """Create the canonical default accounts for a new ledger."""
    accounts = []
    for name, acct_type in DEFAULT_ACCOUNTS:
        acct = Account(
            ledger_id=ledger_id,
            account_type=acct_type,
            name=name,
            normal_balance=NORMAL_BALANCE_MAP[acct_type],
        )
        db.add(acct)
        accounts.append(acct)
    return accounts


# ── Internal Primitives ──────────────────────────────────────────────────────
# These write journal lines. They do NOT validate balance — the caller
# (journalize_transaction) must ensure debits == credits before committing.

def _debit_account(db: Session, entry: JournalEntry, account: Account, amount: Decimal, memo: str = None) -> JournalLine:
    """Add a debit line to a journal entry."""
    line = JournalLine(
        journal_entry_id=entry.id,
        account_id=account.id,
        debit=amount,
        credit=Decimal("0"),
        memo=memo,
    )
    db.add(line)
    return line


def _credit_account(db: Session, entry: JournalEntry, account: Account, amount: Decimal, memo: str = None) -> JournalLine:
    """Add a credit line to a journal entry."""
    line = JournalLine(
        journal_entry_id=entry.id,
        account_id=account.id,
        debit=Decimal("0"),
        credit=amount,
        memo=memo,
    )
    db.add(line)
    return line


# Convenience aliases — the account_type check happens in journalize_transaction,
# not here. These exist so calling code reads naturally.
def _debit_asset(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_asset(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)

def _debit_liability(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_liability(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)

def _debit_equity(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_equity(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)

def _debit_revenue(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_revenue(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)

def _debit_expense(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_expense(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)


# Dispatch table: (account_type, side) → primitive function
_PRIMITIVE_DISPATCH = {
    (AccountType.ASSET, "debit"): _debit_asset,
    (AccountType.ASSET, "credit"): _credit_asset,
    (AccountType.LIABILITY, "debit"): _debit_liability,
    (AccountType.LIABILITY, "credit"): _credit_liability,
    (AccountType.EQUITY, "debit"): _debit_equity,
    (AccountType.EQUITY, "credit"): _credit_equity,
    (AccountType.REVENUE, "debit"): _debit_revenue,
    (AccountType.REVENUE, "credit"): _credit_revenue,
    (AccountType.EXPENSE, "debit"): _debit_expense,
    (AccountType.EXPENSE, "credit"): _credit_expense,
}


def _get_account_balance(db: Session, account: Account, as_of: date = None) -> Decimal:
    """Compute the current balance of an account.

    For debit-normal accounts (asset, expense): balance = sum(debits) - sum(credits)
    For credit-normal accounts (liability, equity, revenue): balance = sum(credits) - sum(debits)
    """
    from sqlalchemy import func
    query = db.query(
        func.coalesce(func.sum(JournalLine.debit), Decimal("0")).label("total_debit"),
        func.coalesce(func.sum(JournalLine.credit), Decimal("0")).label("total_credit"),
    ).join(JournalEntry).filter(
        JournalLine.account_id == account.id,
        JournalEntry.is_void == False,
    )
    if as_of:
        query = query.filter(JournalEntry.date <= as_of)
    row = query.one()

    if account.normal_balance == NormalBalance.DEBIT:
        return row.total_debit - row.total_credit
    else:
        return row.total_credit - row.total_debit


# ── Tool registry (populated by subsequent tasks) ────────────────────────────

ACCOUNTING_TOOLS = []
