# tools/accounting.py
"""Accounting tools: double-entry bookkeeping, inventory, reporting.

21 LLM-facing tools backed by PostgreSQL.
Uses standardized output: {"status": "success"|"error", "data": ..., "error": ""}
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from langchain.tools import tool
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


# ── Ledger Setup Tools ───────────────────────────────────────────────────────

def _create_ledger_impl(db: Session, user_id: str, name: str = "My Ledger") -> str:
    existing = _get_ledger(db, user_id)
    if existing:
        return tool_result(error=f"User already has a ledger (id={existing.id})")

    ledger = Ledger(user_id=user_id, name=name)
    db.add(ledger)
    db.flush()

    accounts = _create_default_accounts(db, ledger.id)
    db.flush()

    return tool_result(data={
        "ledger_id": ledger.id,
        "name": ledger.name,
        "currency": ledger.currency,
        "accounts_created": [
            {"name": a.name, "type": a.account_type.value, "normal_balance": a.normal_balance.value}
            for a in accounts
        ],
    })


@tool
def create_ledger(name: str = "My Ledger") -> str:
    """Initialize a new accounting ledger for the current user.

    WHEN TO USE: When a user wants to start using accounting tools for the first time.
    WHEN NOT TO USE: When the user already has a ledger (will return an error).

    Creates a ledger with 12 default accounts: Cash, Accounts Receivable, Inventory,
    Accounts Payable, Owner's Capital, Income Summary, Revenue, Cost of Goods Sold,
    Rent Expense, Utilities Expense, Supplies Expense, Wages Expense.

    Args:
        name: Name for the ledger (e.g. "My Business", "Personal"). Default: "My Ledger".

    Output format:
        {"status": "success", "data": {"ledger_id": N, "name": "...", "accounts_created": [...]}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _create_ledger_impl(db, current_user.id, name)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


def _create_account_impl(
    db: Session, user_id: str, name: str, account_type: str,
    account_number: str = None, parent_id: int = None,
) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    try:
        acct_type = AccountType(account_type.lower())
    except ValueError:
        return tool_result(error=f"Invalid account_type '{account_type}'. Must be one of: asset, liability, equity, revenue, expense.")

    existing = db.query(Account).filter_by(ledger_id=ledger.id, name=name).first()
    if existing:
        return tool_result(error=f"Account '{name}' already exists in this ledger.")

    if parent_id:
        parent = db.query(Account).filter_by(id=parent_id, ledger_id=ledger.id).first()
        if not parent:
            return tool_result(error=f"Parent account id={parent_id} not found in this ledger.")

    acct = Account(
        ledger_id=ledger.id,
        account_type=acct_type,
        name=name,
        account_number=account_number,
        parent_id=parent_id,
        normal_balance=NORMAL_BALANCE_MAP[acct_type],
    )
    db.add(acct)
    db.flush()

    return tool_result(data={
        "account_id": acct.id,
        "name": acct.name,
        "account_type": acct.account_type.value,
        "account_number": acct.account_number,
        "normal_balance": acct.normal_balance.value,
    })


@tool
def create_account(name: str, account_type: str, account_number: str = None, parent_id: int = None) -> str:
    """Add a new account to the user's chart of accounts.

    WHEN TO USE: When the user needs a new account not in the defaults.
    WHEN NOT TO USE: When the account already exists (will return error).

    Args:
        name: Account name. Must be unique within the ledger.
        account_type: One of: "asset", "liability", "equity", "revenue", "expense".
        account_number: Optional user-assigned number (e.g. "1500"). Must be unique if provided.
        parent_id: Optional parent account ID for sub-accounts.

    Output format:
        {"status": "success", "data": {"account_id": N, "name": "...", "account_type": "...", "normal_balance": "..."}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _create_account_impl(db, current_user.id, name, account_type, account_number, parent_id)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


def _list_accounts_impl(db: Session, user_id: str, account_type: str = None) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    query = db.query(Account).filter_by(ledger_id=ledger.id)
    if account_type:
        try:
            at = AccountType(account_type.lower())
        except ValueError:
            return tool_result(error=f"Invalid account_type '{account_type}'.")
        query = query.filter_by(account_type=at)

    accounts = query.order_by(Account.account_type, Account.name).all()
    return tool_result(data={
        "count": len(accounts),
        "accounts": [
            {
                "id": a.id,
                "name": a.name,
                "account_type": a.account_type.value,
                "account_number": a.account_number,
                "normal_balance": a.normal_balance.value,
                "is_active": a.is_active,
            }
            for a in accounts
        ],
    })


@tool
def list_accounts(account_type: str = None) -> str:
    """List all accounts in the user's chart of accounts.

    WHEN TO USE: When you need to see available accounts before journalizing.
    WHEN NOT TO USE: Never — this is always safe to call.

    Args:
        account_type: Optional filter. One of: "asset", "liability", "equity", "revenue", "expense".
                      If omitted, returns all accounts.

    Output format:
        {"status": "success", "data": {"count": N, "accounts": [{"id": N, "name": "...", ...}]}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _list_accounts_impl(db, current_user.id, account_type)
    finally:
        db.close()


def _get_account_balance_impl(db: Session, user_id: str, account_name: str, as_of_date: str = None) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    account = _resolve_account(db, ledger.id, account_name)
    if not account:
        return tool_result(error=f"Account '{account_name}' not found or inactive.")

    as_of = None
    if as_of_date:
        try:
            as_of = _parse_date(as_of_date)
        except ValueError:
            return tool_result(error=f"Invalid date format '{as_of_date}'. Use YYYY-MM-DD.")

    balance = _get_account_balance(db, account, as_of)

    return tool_result(data={
        "account_name": account.name,
        "account_type": account.account_type.value,
        "normal_balance": account.normal_balance.value,
        "balance": str(balance),
        "as_of_date": as_of_date or "current",
    })


@tool
def get_account_balance(account_name: str, as_of_date: str = None) -> str:
    """Get the current balance of a single account.

    WHEN TO USE: When you need to check one account's balance (e.g. "How much cash do I have?").
    WHEN NOT TO USE: When you need all account balances (use trial_balance instead).

    Args:
        account_name: Exact account name (e.g. "Cash", "Accounts Receivable").
        as_of_date: Optional date in YYYY-MM-DD format. Defaults to all time.

    Output format:
        {"status": "success", "data": {"account_name": "...", "balance": "123.45", ...}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _get_account_balance_impl(db, current_user.id, account_name, as_of_date)
    finally:
        db.close()


def _update_account_impl(
    db: Session, user_id: str, account_name: str,
    new_name: str = None, new_account_number: str = None, is_active: bool = None,
) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    account = db.query(Account).filter_by(ledger_id=ledger.id, name=account_name).first()
    if not account:
        return tool_result(error=f"Account '{account_name}' not found.")

    if new_name:
        existing = db.query(Account).filter_by(ledger_id=ledger.id, name=new_name).first()
        if existing and existing.id != account.id:
            return tool_result(error=f"Account name '{new_name}' already exists.")
        account.name = new_name

    if new_account_number is not None:
        account.account_number = new_account_number

    if is_active is not None:
        if not is_active:
            balance = _get_account_balance(db, account)
            if balance != Decimal("0"):
                return tool_result(error=f"Cannot deactivate account '{account_name}' with non-zero balance ({balance}).")
        account.is_active = is_active

    db.flush()

    return tool_result(data={
        "account_id": account.id,
        "name": account.name,
        "account_type": account.account_type.value,
        "account_number": account.account_number,
        "is_active": account.is_active,
    })


@tool
def update_account(account_name: str, new_name: str = None, new_account_number: str = None, is_active: bool = None) -> str:
    """Update an account's name, number, or active status.

    WHEN TO USE: When renaming an account or deactivating one no longer needed.
    WHEN NOT TO USE: When creating a new account (use create_account).

    Cannot deactivate an account with a non-zero balance.

    Args:
        account_name: Current name of the account to update.
        new_name: New name (optional). Must be unique within ledger.
        new_account_number: New account number (optional).
        is_active: Set to false to deactivate (optional). Requires zero balance.

    Output format:
        {"status": "success", "data": {"account_id": N, "name": "...", "is_active": true/false, ...}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _update_account_impl(db, current_user.id, account_name, new_name, new_account_number, is_active)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


# ── Tool registry ─────────────────────────────────────────────────────────────

ACCOUNTING_TOOLS = [
    create_ledger,
    create_account,
    list_accounts,
    get_account_balance,
    update_account,
]
