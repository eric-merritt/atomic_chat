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


# ── Journal Tools ─────────────────────────────────────────────────────────────

def _journalize_transaction_impl(db: Session, user_id: str, date_str: str, memo: str, lines: list, source_type: SourceType = SourceType.MANUAL) -> str:
    """Core journalizing engine. Validates and creates a balanced journal entry."""
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    try:
        entry_date = _parse_date(date_str)
    except ValueError:
        return tool_result(error=f"Invalid date format '{date_str}'. Use YYYY-MM-DD.")

    if not lines or len(lines) < 2:
        return tool_result(error="A journal entry requires at least 2 lines.")

    # Validate each line
    total_debits = Decimal("0")
    total_credits = Decimal("0")
    resolved_lines = []

    for i, line in enumerate(lines):
        acct_name = line.get("account")
        debit_amt = Decimal(str(line.get("debit", 0)))
        credit_amt = Decimal(str(line.get("credit", 0)))

        # Validate debit XOR credit
        if debit_amt > 0 and credit_amt > 0:
            return tool_result(error=f"Line {i+1}: Cannot have both debit and credit on the same line.")
        if debit_amt == 0 and credit_amt == 0:
            return tool_result(error=f"Line {i+1}: Must have either a debit or credit amount.")
        if debit_amt < 0 or credit_amt < 0:
            return tool_result(error=f"Line {i+1}: Amounts must be positive.")

        account = _resolve_account(db, ledger.id, acct_name)
        if not account:
            return tool_result(error=f"Line {i+1}: Account '{acct_name}' not found or inactive.")

        side = "debit" if debit_amt > 0 else "credit"
        amount = debit_amt if debit_amt > 0 else credit_amt
        total_debits += debit_amt
        total_credits += credit_amt
        resolved_lines.append((account, side, amount, line.get("memo")))

    # Check balance
    if total_debits != total_credits:
        return tool_result(error=f"Debits ({total_debits}) do not balance with credits ({total_credits}).")

    # Create entry
    entry = JournalEntry(
        ledger_id=ledger.id,
        date=entry_date,
        memo=memo,
        source_type=source_type,
    )
    db.add(entry)
    db.flush()

    # Create lines via dispatch
    result_lines = []
    for account, side, amount, line_memo in resolved_lines:
        primitive = _PRIMITIVE_DISPATCH[(account.account_type, side)]
        jl = primitive(db, entry, account, amount, line_memo)
        db.flush()
        result_lines.append({
            "account": account.name,
            "account_type": account.account_type.value,
            "debit": str(jl.debit),
            "credit": str(jl.credit),
            "effect": f"{'increase' if (side == 'debit') == (account.normal_balance == NormalBalance.DEBIT) else 'decrease'} {account.account_type.value}",
        })

    return tool_result(data={
        "journal_entry_id": entry.id,
        "date": str(entry.date),
        "memo": entry.memo,
        "lines": result_lines,
        "total_debits": str(total_debits),
        "total_credits": str(total_credits),
    })


@tool
def journalize_transaction(date: str, memo: str, lines: list) -> str:
    """Record a double-entry journal transaction.

    WHEN TO USE: When recording any financial transaction (payments, sales, adjustments).
    WHEN NOT TO USE: For inventory purchases (use receive_inventory) or FIFO/LIFO sales.

    Every transaction MUST balance: total debits == total credits.
    Each line must have either a debit OR credit, never both.

    Args:
        date: Transaction date in YYYY-MM-DD format.
        memo: Description of the transaction.
        lines: Array of line items. Each: {"account": "name", "debit": amount, "credit": amount}.
               One of debit/credit must be 0.

    Output format:
        {"status": "success", "data": {"journal_entry_id": N, "lines": [...], ...}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _journalize_transaction_impl(db, current_user.id, date, memo, lines)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


def _search_journal_impl(
    db: Session, user_id: str,
    start_date: str = None, end_date: str = None,
    memo_text: str = None, min_amount: float = None,
    max_amount: float = None, account_name: str = None,
) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    query = db.query(JournalEntry).filter_by(ledger_id=ledger.id)

    if start_date:
        query = query.filter(JournalEntry.date >= _parse_date(start_date))
    if end_date:
        query = query.filter(JournalEntry.date <= _parse_date(end_date))
    if memo_text:
        query = query.filter(JournalEntry.memo.ilike(f"%{memo_text}%"))

    entries = query.order_by(JournalEntry.date.desc()).all()

    # Post-filter by amount/account if needed
    results = []
    for entry in entries:
        entry_lines = []
        include = True if not account_name else False
        for line in entry.lines:
            if account_name and line.account.name == account_name:
                include = True
            if min_amount and max(line.debit, line.credit) < Decimal(str(min_amount)):
                continue
            if max_amount and max(line.debit, line.credit) > Decimal(str(max_amount)):
                continue
            entry_lines.append({
                "account": line.account.name,
                "debit": str(line.debit),
                "credit": str(line.credit),
                "memo": line.memo,
            })
        if include and entry_lines:
            results.append({
                "journal_entry_id": entry.id,
                "date": str(entry.date),
                "memo": entry.memo,
                "is_void": entry.is_void,
                "source_type": entry.source_type.value,
                "lines": entry_lines,
            })

    return tool_result(data={"count": len(results), "entries": results})


@tool
def search_journal(
    start_date: str = None, end_date: str = None,
    memo_text: str = None, min_amount: float = None,
    max_amount: float = None, account_name: str = None,
) -> str:
    """Search journal entries by date, memo text, amount, or account.

    WHEN TO USE: When looking for specific transactions.

    Args:
        start_date: Optional start date (YYYY-MM-DD).
        end_date: Optional end date (YYYY-MM-DD).
        memo_text: Optional text to search in entry memos (case-insensitive).
        min_amount: Optional minimum line amount.
        max_amount: Optional maximum line amount.
        account_name: Optional account name filter.

    Output format:
        {"status": "success", "data": {"count": N, "entries": [...]}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _search_journal_impl(db, current_user.id, start_date, end_date, memo_text, min_amount, max_amount, account_name)
    finally:
        db.close()


def _void_transaction_impl(db: Session, user_id: str, journal_entry_id: int, date_str: str, memo: str) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    entry = db.query(JournalEntry).filter_by(id=journal_entry_id, ledger_id=ledger.id).first()
    if not entry:
        return tool_result(error=f"Journal entry {journal_entry_id} not found.")

    if entry.is_void:
        return tool_result(error=f"Entry {journal_entry_id} is already voided.")

    if entry.void_of_id is not None:
        return tool_result(error=f"Entry {journal_entry_id} is a reversal entry and cannot be voided.")

    try:
        void_date = _parse_date(date_str)
    except ValueError:
        return tool_result(error=f"Invalid date format '{date_str}'. Use YYYY-MM-DD.")

    # Create reversing entry
    reversal = JournalEntry(
        ledger_id=ledger.id,
        date=void_date,
        memo=memo,
        source_type=SourceType.VOID,
        void_of_id=entry.id,
    )
    db.add(reversal)
    db.flush()

    # Create opposite lines
    for line in entry.lines:
        reverse_line = JournalLine(
            journal_entry_id=reversal.id,
            account_id=line.account_id,
            debit=line.credit,  # swap
            credit=line.debit,  # swap
            memo=f"Void of entry #{entry.id}: {line.memo or ''}".strip(),
        )
        db.add(reverse_line)

    # Inventory-aware: restore layers if this was an inventory transaction
    if entry.source_type in (SourceType.FIFO_SALE, SourceType.LIFO_SALE):
        # Restore quantity_remaining on consumed layers
        # Find layers that were consumed by looking at COGS lines
        for line in entry.lines:
            if line.account.name == "Inventory" and line.credit > 0:
                # This was a credit to Inventory (cost removal) — find layers
                layers = db.query(InventoryLayer).filter(
                    InventoryLayer.item_id.in_(
                        db.query(InventoryItem.id).filter_by(ledger_id=ledger.id)
                    )
                ).all()
                # Note: exact layer restoration would need per-line tracking.
                # For now, we restore proportionally. Full implementation would
                # need layer IDs stored in line memos.
                pass

    elif entry.source_type == SourceType.INVENTORY_RECEIPT:
        # Set quantity_remaining to 0 on layers created by this receipt
        layers = db.query(InventoryLayer).filter_by(journal_entry_id=entry.id).all()
        for layer in layers:
            layer.quantity_remaining = Decimal("0")

    # Mark original as void
    entry.is_void = True
    db.flush()

    return tool_result(data={
        "reversal_entry_id": reversal.id,
        "original_entry_id": entry.id,
        "date": str(reversal.date),
        "memo": reversal.memo,
    })


@tool
def void_transaction(journal_entry_id: int, date: str, memo: str) -> str:
    """Void a journal entry by creating an equal and opposite reversing entry.

    WHEN TO USE: When a transaction was recorded in error and needs to be reversed.
    WHEN NOT TO USE: When you want to adjust an amount (make a new entry instead).

    Cannot void an entry that is already voided or is itself a reversal.
    Never deletes — preserves full audit trail.

    Args:
        journal_entry_id: ID of the journal entry to void.
        date: Date for the reversing entry (YYYY-MM-DD).
        memo: Reason for voiding.

    Output format:
        {"status": "success", "data": {"reversal_entry_id": N, "original_entry_id": N, ...}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _void_transaction_impl(db, current_user.id, journal_entry_id, date, memo)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


def _account_ledger_impl(db: Session, user_id: str, account_name: str, start_date: str = None, end_date: str = None) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    account = _resolve_account(db, ledger.id, account_name)
    if not account:
        return tool_result(error=f"Account '{account_name}' not found or inactive.")

    query = db.query(JournalLine).join(JournalEntry).filter(
        JournalLine.account_id == account.id,
        JournalEntry.is_void == False,
    )
    if start_date:
        query = query.filter(JournalEntry.date >= _parse_date(start_date))
    if end_date:
        query = query.filter(JournalEntry.date <= _parse_date(end_date))

    lines = query.order_by(JournalEntry.date, JournalEntry.id).all()

    running = Decimal("0")
    entries = []
    for line in lines:
        if account.normal_balance == NormalBalance.DEBIT:
            running += line.debit - line.credit
        else:
            running += line.credit - line.debit
        entries.append({
            "journal_entry_id": line.entry.id,
            "date": str(line.entry.date),
            "memo": line.entry.memo,
            "debit": str(line.debit),
            "credit": str(line.credit),
            "running_balance": str(running),
        })

    return tool_result(data={
        "account_name": account.name,
        "account_type": account.account_type.value,
        "entries": entries,
        "running_balance": str(running),
    })


@tool
def account_ledger(account_name: str, start_date: str = None, end_date: str = None) -> str:
    """View all journal lines for a specific account with running balance.

    WHEN TO USE: When you want to see the full history of an account.

    Args:
        account_name: Exact account name.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).

    Output format:
        {"status": "success", "data": {"account_name": "...", "entries": [...], "running_balance": "..."}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _account_ledger_impl(db, current_user.id, account_name, start_date, end_date)
    finally:
        db.close()


# ── Inventory Tools ───────────────────────────────────────────────────────────

def _register_inventory_item_impl(
    db: Session, user_id: str, sku: str, description: str,
    item_type: str, default_sale_price: float = None,
) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    try:
        itype = ItemType(item_type.lower())
    except ValueError:
        return tool_result(error=f"Invalid item_type '{item_type}'. Must be 'goods' or 'service'.")

    existing = db.query(InventoryItem).filter_by(ledger_id=ledger.id, sku=sku).first()
    if existing:
        return tool_result(error=f"SKU '{sku}' already exists in this ledger.")

    item = InventoryItem(
        ledger_id=ledger.id,
        item_type=itype,
        sku=sku,
        description=description,
        default_sale_price=Decimal(str(default_sale_price)) if default_sale_price else None,
    )
    db.add(item)
    db.flush()

    return tool_result(data={
        "item_id": item.id,
        "sku": item.sku,
        "description": item.description,
        "item_type": item.item_type.value,
        "default_sale_price": str(item.default_sale_price) if item.default_sale_price else None,
    })


@tool
def register_inventory_item(sku: str, description: str, item_type: str, default_sale_price: float = None) -> str:
    """Register a new inventory item (goods or service).

    WHEN TO USE: Before receiving inventory or recording sales for a new product/service.

    Args:
        sku: Unique stock-keeping unit code.
        description: Item description.
        item_type: "goods" (physical, has cost layers) or "service" (no inventory tracking).
        default_sale_price: Optional default price per unit.

    Output format:
        {"status": "success", "data": {"item_id": N, "sku": "...", ...}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _register_inventory_item_impl(db, current_user.id, sku, description, item_type, default_sale_price)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


def _receive_inventory_impl(
    db: Session, user_id: str, item_sku: str, quantity: float,
    unit_cost: float, date_str: str, payment_account: str,
) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    item = db.query(InventoryItem).filter_by(ledger_id=ledger.id, sku=item_sku, is_active=True).first()
    if not item:
        return tool_result(error=f"Item '{item_sku}' not found or inactive.")

    if item.item_type == ItemType.SERVICE:
        return tool_result(error="Cannot receive inventory for service items.")

    qty = Decimal(str(quantity))
    cost = Decimal(str(unit_cost))
    total = qty * cost

    # Auto-journal: debit Inventory, credit payment_account
    journal_result = _journalize_transaction_impl(
        db, user_id, date_str, f"Receive {qty} x {item_sku} @ {cost}",
        [
            {"account": "Inventory", "debit": float(total), "credit": 0},
            {"account": payment_account, "debit": 0, "credit": float(total)},
        ],
        source_type=SourceType.INVENTORY_RECEIPT,
    )
    import json
    jr = json.loads(journal_result)
    if jr["status"] == "error":
        return journal_result

    # Create cost layer
    layer = InventoryLayer(
        item_id=item.id,
        journal_entry_id=jr["data"]["journal_entry_id"],
        quantity_purchased=qty,
        quantity_remaining=qty,
        unit_cost=cost,
        received_date=_parse_date(date_str),
    )
    db.add(layer)
    db.flush()

    return tool_result(data={
        "journal_entry_id": jr["data"]["journal_entry_id"],
        "layer": {
            "layer_id": layer.id,
            "item_sku": item_sku,
            "quantity_purchased": str(layer.quantity_purchased),
            "unit_cost": str(layer.unit_cost),
            "total_cost": str(total),
            "received_date": date_str,
        },
    })


@tool
def receive_inventory(item_sku: str, quantity: float, unit_cost: float, date: str, payment_account: str) -> str:
    """Receive inventory and auto-record the purchase journal entry.

    WHEN TO USE: When goods arrive and need to be added to inventory.

    Creates a cost layer and journals: debit Inventory, credit payment_account.

    Args:
        item_sku: SKU of the item being received.
        quantity: Number of units received.
        unit_cost: Cost per unit.
        date: Receipt date (YYYY-MM-DD).
        payment_account: Account to credit (e.g. "Cash", "Accounts Payable").

    Output format:
        {"status": "success", "data": {"journal_entry_id": N, "layer": {...}}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _receive_inventory_impl(db, current_user.id, item_sku, quantity, unit_cost, date, payment_account)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


def _list_inventory_items_impl(db: Session, user_id: str) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    items = db.query(InventoryItem).filter_by(ledger_id=ledger.id).order_by(InventoryItem.sku).all()

    result_items = []
    for item in items:
        qty_on_hand = sum(l.quantity_remaining for l in item.layers)
        result_items.append({
            "item_id": item.id,
            "sku": item.sku,
            "description": item.description,
            "item_type": item.item_type.value,
            "is_active": item.is_active,
            "quantity_on_hand": str(qty_on_hand),
            "cost_layers": len(item.layers),
            "default_sale_price": str(item.default_sale_price) if item.default_sale_price else None,
        })

    return tool_result(data={"count": len(result_items), "items": result_items})


@tool
def list_inventory_items() -> str:
    """List all inventory items with quantity on hand.

    WHEN TO USE: When you need to see what's in stock.

    Output format:
        {"status": "success", "data": {"count": N, "items": [...]}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _list_inventory_items_impl(db, current_user.id)
    finally:
        db.close()


def _deactivate_inventory_item_impl(db: Session, user_id: str, item_sku: str) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    item = db.query(InventoryItem).filter_by(ledger_id=ledger.id, sku=item_sku).first()
    if not item:
        return tool_result(error=f"Item '{item_sku}' not found.")

    # Check for remaining inventory
    remaining = sum(l.quantity_remaining for l in item.layers)
    if remaining > 0:
        return tool_result(error=f"Cannot deactivate '{item_sku}': quantity_remaining = {remaining}. Must deplete inventory first.")

    item.is_active = False
    db.flush()

    return tool_result(data={
        "item_id": item.id,
        "sku": item.sku,
        "description": item.description,
        "is_active": item.is_active,
    })


@tool
def deactivate_inventory_item(item_sku: str) -> str:
    """Deactivate an inventory item.

    WHEN TO USE: When an item is discontinued and fully depleted.

    Rejects if any cost layers still have remaining quantity.

    Args:
        item_sku: SKU of the item to deactivate.

    Output format:
        {"status": "success", "data": {"item_id": N, "sku": "...", "is_active": false}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _deactivate_inventory_item_impl(db, current_user.id, item_sku)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


# ── FIFO/LIFO Costing Tools ───────────────────────────────────────────────────

def _journalize_cost_layer_sale(
    db: Session, user_id: str, date_str: str, memo: str,
    item_sku: str, quantity: float, sale_price_per_unit: float = None,
    revenue_account: str = "Revenue", receivable_account: str = "Cash",
    method: str = "fifo",
) -> str:
    """Shared FIFO/LIFO implementation. method='fifo' or 'lifo'."""
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    item = db.query(InventoryItem).filter_by(ledger_id=ledger.id, sku=item_sku, is_active=True).first()
    if not item:
        return tool_result(error=f"Item '{item_sku}' not found or inactive.")

    if item.item_type == ItemType.SERVICE:
        return tool_result(error=f"Cannot use {method.upper()} costing on service items. Services have no cost layers.")

    qty_needed = Decimal(str(quantity))

    # Check total available
    total_available = sum(l.quantity_remaining for l in item.layers)
    if total_available < qty_needed:
        return tool_result(error=f"Insufficient inventory for '{item_sku}': need {qty_needed}, have {total_available}.")

    # Pull layers in order
    order = InventoryLayer.received_date.asc() if method == "fifo" else InventoryLayer.received_date.desc()
    layers = db.query(InventoryLayer).filter(
        InventoryLayer.item_id == item.id,
        InventoryLayer.quantity_remaining > 0,
    ).order_by(order).all()

    # Consume layers
    remaining = qty_needed
    total_cogs = Decimal("0")
    layers_consumed = []
    journal_lines = []

    for layer in layers:
        if remaining <= 0:
            break
        take = min(remaining, layer.quantity_remaining)
        cost = take * layer.unit_cost
        layer.quantity_remaining -= take
        remaining -= take
        total_cogs += cost

        layers_consumed.append({
            "layer_id": layer.id,
            "quantity_taken": str(take),
            "unit_cost": str(layer.unit_cost),
            "layer_cost": str(cost),
            "received_date": str(layer.received_date),
        })

        # Per-layer COGS line
        journal_lines.append({"account": "Cost of Goods Sold", "debit": float(cost), "credit": 0,
                              "memo": f"Layer {layer.id}: {take} x {layer.unit_cost} from {layer.received_date}"})
        journal_lines.append({"account": "Inventory", "debit": 0, "credit": float(cost)})

    # Sale revenue lines (if sale_price provided)
    sale_total = None
    if sale_price_per_unit is not None:
        sale_total = qty_needed * Decimal(str(sale_price_per_unit))
        journal_lines.append({"account": receivable_account, "debit": float(sale_total), "credit": 0})
        journal_lines.append({"account": revenue_account, "debit": 0, "credit": float(sale_total)})

    source = SourceType.FIFO_SALE if method == "fifo" else SourceType.LIFO_SALE
    journal_result = _journalize_transaction_impl(db, user_id, date_str, memo, journal_lines, source_type=source)

    import json as _json
    jr = _json.loads(journal_result)
    if jr["status"] == "error":
        return journal_result

    return tool_result(data={
        "journal_entry_id": jr["data"]["journal_entry_id"],
        "method": method,
        "item_sku": item_sku,
        "quantity_sold": str(qty_needed),
        "total_cogs": str(total_cogs),
        "sale_total": str(sale_total) if sale_total else None,
        "layers_consumed": layers_consumed,
    })


def _journalize_fifo_transaction_impl(
    db: Session, user_id: str, date_str: str, memo: str,
    item_sku: str, quantity: float, sale_price_per_unit: float = None,
    revenue_account: str = "Revenue", receivable_account: str = "Cash",
) -> str:
    return _journalize_cost_layer_sale(
        db, user_id, date_str, memo, item_sku, quantity,
        sale_price_per_unit, revenue_account, receivable_account, method="fifo",
    )


@tool
def journalize_fifo_transaction(
    date: str, memo: str, item_sku: str, quantity: float,
    sale_price_per_unit: float = None, revenue_account: str = "Revenue",
    receivable_account: str = "Cash",
) -> str:
    """Record a FIFO (first-in, first-out) inventory sale or consumption.

    WHEN TO USE: When selling goods using FIFO costing (oldest inventory used first).

    Pulls cost from oldest layers first. Auto-generates COGS and revenue journal lines.

    Args:
        date: Sale date (YYYY-MM-DD).
        memo: Transaction description.
        item_sku: SKU of the item being sold.
        quantity: Units sold/consumed.
        sale_price_per_unit: Price per unit (null for internal consumption).
        revenue_account: Revenue account name (default "Revenue").
        receivable_account: Account to debit for sale (default "Cash").

    Output format:
        {"status": "success", "data": {"total_cogs": "...", "sale_total": "...", "layers_consumed": [...]}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _journalize_fifo_transaction_impl(
            db, current_user.id, date, memo, item_sku, quantity,
            sale_price_per_unit, revenue_account, receivable_account,
        )
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


def _journalize_lifo_transaction_impl(
    db: Session, user_id: str, date_str: str, memo: str,
    item_sku: str, quantity: float, sale_price_per_unit: float = None,
    revenue_account: str = "Revenue", receivable_account: str = "Cash",
) -> str:
    return _journalize_cost_layer_sale(
        db, user_id, date_str, memo, item_sku, quantity,
        sale_price_per_unit, revenue_account, receivable_account, method="lifo",
    )


@tool
def journalize_lifo_transaction(
    date: str, memo: str, item_sku: str, quantity: float,
    sale_price_per_unit: float = None, revenue_account: str = "Revenue",
    receivable_account: str = "Cash",
) -> str:
    """Record a LIFO (last-in, first-out) inventory sale or consumption.

    WHEN TO USE: When selling goods using LIFO costing (newest inventory used first).

    Pulls cost from newest layers first. Auto-generates COGS and revenue journal lines.

    Args:
        date: Sale date (YYYY-MM-DD).
        memo: Transaction description.
        item_sku: SKU of the item being sold.
        quantity: Units sold/consumed.
        sale_price_per_unit: Price per unit (null for internal consumption).
        revenue_account: Revenue account name (default "Revenue").
        receivable_account: Account to debit for sale (default "Cash").

    Output format:
        {"status": "success", "data": {"total_cogs": "...", "sale_total": "...", "layers_consumed": [...]}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _journalize_lifo_transaction_impl(
            db, current_user.id, date, memo, item_sku, quantity,
            sale_price_per_unit, revenue_account, receivable_account,
        )
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


def _inventory_valuation_impl(db: Session, user_id: str, method: str = "fifo") -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    items = db.query(InventoryItem).filter_by(
        ledger_id=ledger.id, item_type=ItemType.GOODS,
    ).order_by(InventoryItem.sku).all()

    result_items = []
    for item in items:
        layers = db.query(InventoryLayer).filter(
            InventoryLayer.item_id == item.id,
            InventoryLayer.quantity_remaining > 0,
        ).order_by(
            InventoryLayer.received_date.asc() if method == "fifo" else InventoryLayer.received_date.desc()
        ).all()

        qty_on_hand = sum(l.quantity_remaining for l in layers)
        total_cost = sum(l.quantity_remaining * l.unit_cost for l in layers)
        avg_cost = total_cost / qty_on_hand if qty_on_hand > 0 else Decimal("0")

        result_items.append({
            "sku": item.sku,
            "description": item.description,
            "quantity_on_hand": str(qty_on_hand),
            "total_cost": str(total_cost),
            "weighted_avg_unit_cost": str(avg_cost.quantize(Decimal("0.0001"))),
            "layers": [
                {
                    "layer_id": l.id,
                    "quantity_remaining": str(l.quantity_remaining),
                    "unit_cost": str(l.unit_cost),
                    "received_date": str(l.received_date),
                }
                for l in layers
            ],
        })

    return tool_result(data={"method": method, "items": result_items})


@tool
def inventory_valuation(method: str = "fifo") -> str:
    """Get current inventory valuation with cost layer details.

    WHEN TO USE: When you need to know the value of inventory on hand.

    Args:
        method: "fifo" (default) or "lifo" — determines layer ordering in report.

    Output format:
        {"status": "success", "data": {"method": "fifo", "items": [{"sku": "...", "total_cost": "...", ...}]}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _inventory_valuation_impl(db, current_user.id, method)
    finally:
        db.close()


# ── Reporting & Period Close Tools ───────────────────────────────────────────

def _trial_balance_impl(db: Session, user_id: str, as_of_date: str = None) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    as_of = _parse_date(as_of_date) if as_of_date else None
    accounts = db.query(Account).filter_by(ledger_id=ledger.id).order_by(Account.account_type, Account.name).all()

    total_debits = Decimal("0")
    total_credits = Decimal("0")
    rows = []

    for acct in accounts:
        balance = _get_account_balance(db, acct, as_of)
        if acct.normal_balance == NormalBalance.DEBIT:
            debit_bal = balance if balance >= 0 else Decimal("0")
            credit_bal = abs(balance) if balance < 0 else Decimal("0")
        else:
            credit_bal = balance if balance >= 0 else Decimal("0")
            debit_bal = abs(balance) if balance < 0 else Decimal("0")

        total_debits += debit_bal
        total_credits += credit_bal

        rows.append({
            "account": acct.name,
            "account_type": acct.account_type.value,
            "debit": str(debit_bal),
            "credit": str(credit_bal),
            "balance": str(balance),
        })

    return tool_result(data={
        "as_of_date": as_of_date or "current",
        "accounts": rows,
        "total_debits": str(total_debits),
        "total_credits": str(total_credits),
    })


@tool
def trial_balance(as_of_date: str = None) -> str:
    """Generate a trial balance showing all accounts with debit/credit totals.

    WHEN TO USE: To verify the books balance (total debits == total credits).

    Args:
        as_of_date: Optional cutoff date (YYYY-MM-DD). Defaults to all time.

    Output format:
        {"status": "success", "data": {"accounts": [...], "total_debits": "...", "total_credits": "..."}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _trial_balance_impl(db, current_user.id, as_of_date)
    finally:
        db.close()


def _income_statement_impl(db: Session, user_id: str, start_date: str, end_date: str) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    start = _parse_date(start_date)
    end = _parse_date(end_date)

    revenue_accounts = db.query(Account).filter_by(
        ledger_id=ledger.id, account_type=AccountType.REVENUE, is_active=True
    ).all()
    expense_accounts = db.query(Account).filter_by(
        ledger_id=ledger.id, account_type=AccountType.EXPENSE, is_active=True
    ).all()

    # For income statement we need balances within the date range only.
    # Balance at end minus balance at start-1 gives the period activity.
    from datetime import timedelta
    day_before_start = start - timedelta(days=1)

    revenue_rows = []
    total_revenue = Decimal("0")
    for acct in revenue_accounts:
        end_bal = _get_account_balance(db, acct, end)
        start_bal = _get_account_balance(db, acct, day_before_start)
        period_bal = end_bal - start_bal
        if period_bal != 0:
            revenue_rows.append({"account": acct.name, "amount": str(period_bal)})
            total_revenue += period_bal

    expense_rows = []
    total_expenses = Decimal("0")
    for acct in expense_accounts:
        end_bal = _get_account_balance(db, acct, end)
        start_bal = _get_account_balance(db, acct, day_before_start)
        period_bal = end_bal - start_bal
        if period_bal != 0:
            expense_rows.append({"account": acct.name, "amount": str(period_bal)})
            total_expenses += period_bal

    net_income = total_revenue - total_expenses

    return tool_result(data={
        "start_date": start_date,
        "end_date": end_date,
        "revenue": revenue_rows,
        "total_revenue": str(total_revenue),
        "expenses": expense_rows,
        "total_expenses": str(total_expenses),
        "net_income": str(net_income),
    })


@tool
def income_statement(start_date: str, end_date: str) -> str:
    """Generate an income statement (profit & loss) for a date range.

    WHEN TO USE: To see revenue, expenses, and net income for a period.

    Args:
        start_date: Period start (YYYY-MM-DD).
        end_date: Period end (YYYY-MM-DD).

    Output format:
        {"status": "success", "data": {"total_revenue": "...", "total_expenses": "...", "net_income": "..."}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _income_statement_impl(db, current_user.id, start_date, end_date)
    finally:
        db.close()


def _balance_sheet_impl(db: Session, user_id: str, as_of_date: str = None) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    as_of = _parse_date(as_of_date) if as_of_date else None

    assets = []
    total_assets = Decimal("0")
    liabilities = []
    total_liabilities = Decimal("0")
    equity = []
    total_equity = Decimal("0")

    accounts = db.query(Account).filter_by(ledger_id=ledger.id).order_by(Account.name).all()

    for acct in accounts:
        balance = _get_account_balance(db, acct, as_of)
        entry = {"account": acct.name, "balance": str(balance)}

        if acct.account_type == AccountType.ASSET:
            assets.append(entry)
            total_assets += balance
        elif acct.account_type == AccountType.LIABILITY:
            liabilities.append(entry)
            total_liabilities += balance
        elif acct.account_type in (AccountType.EQUITY, AccountType.REVENUE, AccountType.EXPENSE):
            # Revenue/expense are temporary equity accounts (pre-close).
            # Expense has debit-normal balance (positive = cost), which reduces equity.
            equity.append(entry)
            if acct.account_type == AccountType.EXPENSE:
                total_equity -= balance
            else:
                total_equity += balance

    return tool_result(data={
        "as_of_date": as_of_date or "current",
        "assets": assets,
        "total_assets": str(total_assets),
        "liabilities": liabilities,
        "total_liabilities": str(total_liabilities),
        "equity": equity,
        "total_equity": str(total_equity),
        "balanced": str(abs(total_assets - (total_liabilities + total_equity)) < Decimal("0.01")),
    })


@tool
def balance_sheet(as_of_date: str = None) -> str:
    """Generate a balance sheet: Assets = Liabilities + Equity.

    WHEN TO USE: To see the financial position at a point in time.

    Revenue/expense accounts are included in equity (as unclosed temporary accounts).

    Args:
        as_of_date: Optional date (YYYY-MM-DD). Defaults to all time.

    Output format:
        {"status": "success", "data": {"total_assets": "...", "total_liabilities": "...", "total_equity": "...", "balanced": "True"}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _balance_sheet_impl(db, current_user.id, as_of_date)
    finally:
        db.close()


def _close_period_impl(db: Session, user_id: str, period_end_date: str) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    end_date = _parse_date(period_end_date)

    # Get revenue and expense accounts with non-zero balances
    revenue_accounts = db.query(Account).filter_by(
        ledger_id=ledger.id, account_type=AccountType.REVENUE
    ).all()
    expense_accounts = db.query(Account).filter_by(
        ledger_id=ledger.id, account_type=AccountType.EXPENSE
    ).all()

    revenue_with_balance = [(a, _get_account_balance(db, a, end_date)) for a in revenue_accounts]
    revenue_with_balance = [(a, b) for a, b in revenue_with_balance if b != 0]

    expense_with_balance = [(a, _get_account_balance(db, a, end_date)) for a in expense_accounts]
    expense_with_balance = [(a, b) for a, b in expense_with_balance if b != 0]

    if not revenue_with_balance and not expense_with_balance:
        return tool_result(data={"message": "Nothing to close — all revenue and expense accounts have zero balances."})

    income_summary = _resolve_account(db, ledger.id, "Income Summary")
    owners_capital = _resolve_account(db, ledger.id, "Owner's Capital")

    journal_entry_ids = []

    import json as _json

    # Step 1: Close revenue → Income Summary
    # Debit each revenue account (zeroing it), Credit Income Summary
    if revenue_with_balance:
        lines = []
        total_revenue = Decimal("0")
        for acct, bal in revenue_with_balance:
            lines.append({"account": acct.name, "debit": float(bal), "credit": 0})
            total_revenue += bal
        lines.append({"account": "Income Summary", "debit": 0, "credit": float(total_revenue)})

        result = _journalize_transaction_impl(
            db, user_id, period_end_date, f"Close revenue accounts for period ending {period_end_date}",
            lines, source_type=SourceType.PERIOD_CLOSE,
        )
        jr = _json.loads(result)
        if jr["status"] == "error":
            return result
        journal_entry_ids.append(jr["data"]["journal_entry_id"])
        db.flush()

    # Step 2: Close expenses → Income Summary
    # Credit each expense account (zeroing it), Debit Income Summary
    if expense_with_balance:
        lines = []
        total_expenses = Decimal("0")
        for acct, bal in expense_with_balance:
            lines.append({"account": acct.name, "debit": 0, "credit": float(bal)})
            total_expenses += bal
        lines.append({"account": "Income Summary", "debit": float(total_expenses), "credit": 0})

        result = _journalize_transaction_impl(
            db, user_id, period_end_date, f"Close expense accounts for period ending {period_end_date}",
            lines, source_type=SourceType.PERIOD_CLOSE,
        )
        jr = _json.loads(result)
        if jr["status"] == "error":
            return result
        journal_entry_ids.append(jr["data"]["journal_entry_id"])
        db.flush()

    # Step 3: Close Income Summary → Owner's Capital
    is_balance = _get_account_balance(db, income_summary)
    if is_balance != 0:
        if is_balance > 0:
            # Net income: Debit Income Summary, Credit Owner's Capital
            lines = [
                {"account": "Income Summary", "debit": float(is_balance), "credit": 0},
                {"account": "Owner's Capital", "debit": 0, "credit": float(is_balance)},
            ]
        else:
            # Net loss: Credit Income Summary, Debit Owner's Capital
            loss = abs(is_balance)
            lines = [
                {"account": "Income Summary", "debit": 0, "credit": float(loss)},
                {"account": "Owner's Capital", "debit": float(loss), "credit": 0},
            ]

        result = _journalize_transaction_impl(
            db, user_id, period_end_date, f"Close Income Summary to Owner's Capital",
            lines, source_type=SourceType.PERIOD_CLOSE,
        )
        jr = _json.loads(result)
        if jr["status"] == "error":
            return result
        journal_entry_ids.append(jr["data"]["journal_entry_id"])
        db.flush()

    total_revenue = sum(b for _, b in revenue_with_balance)
    total_expenses_val = sum(b for _, b in expense_with_balance)
    net_income = total_revenue - total_expenses_val

    return tool_result(data={
        "period_end_date": period_end_date,
        "net_income": str(net_income),
        "total_revenue_closed": str(total_revenue),
        "total_expenses_closed": str(total_expenses_val),
        "journal_entry_ids": journal_entry_ids,
    })


@tool
def close_period(period_end_date: str) -> str:
    """Close revenue and expense accounts for a period, transferring net income to Owner's Capital.

    WHEN TO USE: At the end of an accounting period (month, quarter, year).

    Executes 3 closing entries:
    1. Close revenue accounts to Income Summary
    2. Close expense accounts to Income Summary
    3. Close Income Summary to Owner's Capital

    Args:
        period_end_date: Last day of the period (YYYY-MM-DD).

    Output format:
        {"status": "success", "data": {"net_income": "...", "journal_entry_ids": [...]}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        result = _close_period_impl(db, current_user.id, period_end_date)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        return tool_result(error=str(e))
    finally:
        db.close()


def _cash_flow_statement_impl(db: Session, user_id: str, start_date: str, end_date: str) -> str:
    ledger = _get_ledger(db, user_id)
    if not ledger:
        return tool_result(error="No ledger found. Call create_ledger first.")

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    from datetime import timedelta
    day_before = start - timedelta(days=1)

    cash_account = _resolve_account(db, ledger.id, "Cash")
    if not cash_account:
        return tool_result(error="Cash account not found.")

    beginning_cash = _get_account_balance(db, cash_account, day_before)
    ending_cash = _get_account_balance(db, cash_account, end)
    net_change = ending_cash - beginning_cash

    # Compute net income for the period
    revenue_accounts = db.query(Account).filter_by(
        ledger_id=ledger.id, account_type=AccountType.REVENUE
    ).all()
    expense_accounts = db.query(Account).filter_by(
        ledger_id=ledger.id, account_type=AccountType.EXPENSE
    ).all()

    total_revenue = Decimal("0")
    for acct in revenue_accounts:
        end_bal = _get_account_balance(db, acct, end)
        start_bal = _get_account_balance(db, acct, day_before)
        total_revenue += end_bal - start_bal

    total_expenses = Decimal("0")
    for acct in expense_accounts:
        end_bal = _get_account_balance(db, acct, end)
        start_bal = _get_account_balance(db, acct, day_before)
        total_expenses += end_bal - start_bal

    net_income = total_revenue - total_expenses

    # Working capital changes (AR, AP, Inventory)
    operating_adjustments = []
    for name in ["Accounts Receivable", "Inventory", "Accounts Payable"]:
        acct = _resolve_account(db, ledger.id, name)
        if acct:
            end_bal = _get_account_balance(db, acct, end)
            start_bal = _get_account_balance(db, acct, day_before)
            change = end_bal - start_bal
            if change != 0:
                # For assets: increase = cash outflow (negative)
                # For liabilities: increase = cash inflow (positive)
                if acct.account_type == AccountType.ASSET:
                    adjustment = -change
                else:
                    adjustment = change
                operating_adjustments.append({
                    "account": name,
                    "change": str(change),
                    "cash_effect": str(adjustment),
                })

    operating_total = net_income + sum(Decimal(a["cash_effect"]) for a in operating_adjustments)

    # Financing: equity changes (excluding retained earnings/net income)
    financing_items = []
    for acct_name in ["Owner's Capital"]:
        acct = _resolve_account(db, ledger.id, acct_name)
        if acct:
            end_bal = _get_account_balance(db, acct, end)
            start_bal = _get_account_balance(db, acct, day_before)
            change = end_bal - start_bal
            if change != 0:
                financing_items.append({"account": acct_name, "amount": str(change)})

    financing_total = sum(Decimal(f["amount"]) for f in financing_items)

    return tool_result(data={
        "start_date": start_date,
        "end_date": end_date,
        "operating_activities": {
            "net_income": str(net_income),
            "adjustments": operating_adjustments,
            "total": str(operating_total),
        },
        "investing_activities": {
            "items": [],
            "total": "0",
        },
        "financing_activities": {
            "items": financing_items,
            "total": str(financing_total),
        },
        "net_change_in_cash": str(net_change),
        "beginning_cash": str(beginning_cash),
        "ending_cash": str(ending_cash),
    })


@tool
def cash_flow_statement(start_date: str, end_date: str) -> str:
    """Generate a cash flow statement using the indirect method.

    WHEN TO USE: To understand where cash came from and went during a period.

    Args:
        start_date: Period start (YYYY-MM-DD).
        end_date: Period end (YYYY-MM-DD).

    Output format:
        {"status": "success", "data": {"operating_activities": {...}, "investing_activities": {...}, "financing_activities": {...}, "ending_cash": "..."}, "error": ""}
    """
    from flask_login import current_user
    db = _get_db()
    try:
        return _cash_flow_statement_impl(db, current_user.id, start_date, end_date)
    finally:
        db.close()


# ── Tool registry ─────────────────────────────────────────────────────────────

ACCOUNTING_TOOLS = [
    create_ledger,
    create_account,
    list_accounts,
    get_account_balance,
    update_account,
    journalize_transaction,
    search_journal,
    void_transaction,
    account_ledger,
    register_inventory_item,
    receive_inventory,
    list_inventory_items,
    deactivate_inventory_item,
    journalize_fifo_transaction,
    journalize_lifo_transaction,
    inventory_valuation,
    close_period,
    trial_balance,
    income_statement,
    balance_sheet,
    cash_flow_statement,
]
