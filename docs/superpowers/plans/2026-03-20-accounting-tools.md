# Accounting Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 21-tool double-entry accounting system backed by PostgreSQL, integrated into the existing agent framework.

**Architecture:** New SQLAlchemy models in `auth/accounting_models.py` (6 tables). Tools in `tools/accounting.py` with 10 internal primitives dispatched by `journalize_transaction`. All tools return standardized JSON via `tools/_output.py:tool_result()`. Each user gets an isolated ledger keyed by `user_id`.

**Tech Stack:** Python, SQLAlchemy (existing PostgreSQL), LangChain `@tool`, psycopg2.

**Spec:** `docs/superpowers/specs/2026-03-20-accounting-tools-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `tools/_output.py` | **Create** | Shared `tool_result()` JSON helper |
| `auth/accounting_models.py` | **Create** | 6 SQLAlchemy models (ledgers, accounts, journal_entries, journal_lines, inventory_items, inventory_layers) |
| `tools/accounting.py` | **Create** | 21 @tool functions + 10 `_debit_*`/`_credit_*` primitives |
| `migrations/add_accounting_tables.sql` | **Create** | Raw SQL migration for the 6 tables + enums + constraints |
| `tools/__init__.py` | **Modify** | Import and add ACCOUNTING_TOOLS to ALL_TOOLS |
| `tests/test_output_helper.py` | **Create** | Tests for `tool_result()` helper |
| `tests/test_accounting_models.py` | **Create** | Tests for SQLAlchemy models + migration SQL |
| `tests/test_accounting_primitives.py` | **Create** | Tests for 10 debit/credit primitives |
| `tests/test_accounting_ledger.py` | **Create** | Tests for ledger + account tools (5) |
| `tests/test_accounting_journal.py` | **Create** | Tests for journal tools (4) |
| `tests/test_accounting_inventory.py` | **Create** | Tests for inventory tools (4) |
| `tests/test_accounting_fifo_lifo.py` | **Create** | Tests for FIFO/LIFO + valuation tools (3) |
| `tests/test_accounting_reporting.py` | **Create** | Tests for reporting tools (5) |
| `tests/test_integration_accounting.py` | **Create** | Registry + tools_server integration tests |
| `tests/conftest.py` | **Modify** | Add accounting DB fixtures |

---

## Task 1: Create `tools/_output.py`

**Files:**
- Create: `tools/_output.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_output_helper.py
from tools._output import tool_result
import json

def test_success_result():
    result = tool_result(data={"foo": "bar"})
    parsed = json.loads(result)
    assert parsed["status"] == "success"
    assert parsed["data"] == {"foo": "bar"}
    assert parsed["error"] == ""

def test_error_result():
    result = tool_result(error="something broke")
    parsed = json.loads(result)
    assert parsed["status"] == "error"
    assert parsed["data"] is None
    assert parsed["error"] == "something broke"

def test_success_with_none_data():
    result = tool_result()
    parsed = json.loads(result)
    assert parsed["status"] == "success"
    assert parsed["data"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_output_helper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools._output'`

- [ ] **Step 3: Implement**

```python
# tools/_output.py
"""Standardized tool output format."""

import json


def tool_result(data=None, error: str = "") -> str:
    """Return a standardized JSON response string.

    All tools MUST return the output of this function.

    Args:
        data: The tool's result payload. Any JSON-serializable value.
        error: Error message. If non-empty, status is "error".

    Returns:
        JSON string: {"status": "success"|"error", "data": ..., "error": ""}
    """
    if error:
        return json.dumps({"status": "error", "data": None, "error": error})
    return json.dumps({"status": "success", "data": data, "error": ""})
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_output_helper.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add tools/_output.py tests/test_output_helper.py
git commit -m "feat: add standardized tool output helper"
```

---

## Task 2: Database Models + Migration

**Files:**
- Create: `auth/accounting_models.py`
- Create: `migrations/add_accounting_tables.sql`

- [ ] **Step 1: Write the test**

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `.venv/bin/python -m pytest tests/test_accounting_models.py -v`

- [ ] **Step 3: Implement the models**

```python
# auth/accounting_models.py
"""Accounting domain models — ledgers, accounts, journal entries, inventory."""

import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from auth.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ────────────────────────────────────────────────────────────────────

class AccountType(enum.Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class NormalBalance(enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class ItemType(enum.Enum):
    GOODS = "goods"
    SERVICE = "service"


class SourceType(enum.Enum):
    MANUAL = "manual"
    FIFO_SALE = "fifo_sale"
    LIFO_SALE = "lifo_sale"
    INVENTORY_RECEIPT = "inventory_receipt"
    PERIOD_CLOSE = "period_close"
    VOID = "void"


NORMAL_BALANCE_MAP = {
    AccountType.ASSET: NormalBalance.DEBIT,
    AccountType.EXPENSE: NormalBalance.DEBIT,
    AccountType.LIABILITY: NormalBalance.CREDIT,
    AccountType.EQUITY: NormalBalance.CREDIT,
    AccountType.REVENUE: NormalBalance.CREDIT,
}


# ── Models ───────────────────────────────────────────────────────────────────

class Ledger(Base):
    __tablename__ = "ledgers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    accounts = relationship("Account", back_populates="ledger", cascade="all, delete-orphan")
    journal_entries = relationship("JournalEntry", back_populates="ledger", cascade="all, delete-orphan")
    inventory_items = relationship("InventoryItem", back_populates="ledger", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("ledger_id", "name", name="uq_account_ledger_name"),
        UniqueConstraint("ledger_id", "account_number", name="uq_account_ledger_number"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    ledger_id = Column(Integer, ForeignKey("ledgers.id", ondelete="CASCADE"), nullable=False)
    account_type = Column(Enum(AccountType), nullable=False)
    name = Column(String(255), nullable=False)
    account_number = Column(String(20), nullable=True)
    parent_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    normal_balance = Column(Enum(NormalBalance), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    ledger = relationship("Ledger", back_populates="accounts")
    children = relationship("Account", backref="parent", remote_side=[id])
    journal_lines = relationship("JournalLine", back_populates="account")


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ledger_id = Column(Integer, ForeignKey("ledgers.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    memo = Column(Text, nullable=False)
    is_void = Column(Boolean, default=False, nullable=False)
    void_of_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    source_type = Column(Enum(SourceType), nullable=False, default=SourceType.MANUAL)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    ledger = relationship("Ledger", back_populates="journal_entries")
    lines = relationship("JournalLine", back_populates="entry", cascade="all, delete-orphan")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint(
            "debit >= 0 AND credit >= 0 AND (debit > 0) != (credit > 0)",
            name="ck_journal_line_one_side",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    debit = Column(Numeric(15, 2), default=Decimal("0"), nullable=False)
    credit = Column(Numeric(15, 2), default=Decimal("0"), nullable=False)
    memo = Column(Text, nullable=True)

    entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="journal_lines")


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("ledger_id", "sku", name="uq_inventory_ledger_sku"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    ledger_id = Column(Integer, ForeignKey("ledgers.id", ondelete="CASCADE"), nullable=False)
    item_type = Column(Enum(ItemType), nullable=False)
    sku = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    default_sale_price = Column(Numeric(15, 2), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    ledger = relationship("Ledger", back_populates="inventory_items")
    layers = relationship("InventoryLayer", back_populates="item", cascade="all, delete-orphan")


class InventoryLayer(Base):
    __tablename__ = "inventory_layers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    quantity_purchased = Column(Numeric(15, 4), nullable=False)
    quantity_remaining = Column(Numeric(15, 4), nullable=False)
    unit_cost = Column(Numeric(15, 4), nullable=False)
    received_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    item = relationship("InventoryItem", back_populates="layers")
    journal_entry = relationship("JournalEntry")
```

- [ ] **Step 4: Write the migration SQL**

```sql
-- migrations/add_accounting_tables.sql
-- Accounting module: 6 tables, 4 enums

-- Enums
CREATE TYPE account_type AS ENUM ('asset', 'liability', 'equity', 'revenue', 'expense');
CREATE TYPE normal_balance AS ENUM ('debit', 'credit');
CREATE TYPE item_type AS ENUM ('goods', 'service');
CREATE TYPE source_type AS ENUM ('manual', 'fifo_sale', 'lifo_sale', 'inventory_receipt', 'period_close', 'void');

-- Ledgers
CREATE TABLE ledgers (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Accounts
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
    account_type account_type NOT NULL,
    name VARCHAR(255) NOT NULL,
    account_number VARCHAR(20),
    parent_id INTEGER REFERENCES accounts(id),
    normal_balance normal_balance NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_account_ledger_name UNIQUE (ledger_id, name),
    CONSTRAINT uq_account_ledger_number UNIQUE (ledger_id, account_number)
);

-- Journal Entries
CREATE TABLE journal_entries (
    id SERIAL PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    memo TEXT NOT NULL,
    is_void BOOLEAN NOT NULL DEFAULT FALSE,
    void_of_id INTEGER REFERENCES journal_entries(id),
    source_type source_type NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Journal Lines
CREATE TABLE journal_lines (
    id SERIAL PRIMARY KEY,
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    debit NUMERIC(15,2) NOT NULL DEFAULT 0,
    credit NUMERIC(15,2) NOT NULL DEFAULT 0,
    memo TEXT,
    CONSTRAINT ck_journal_line_one_side CHECK (debit >= 0 AND credit >= 0 AND (debit > 0) != (credit > 0))
);

-- Inventory Items
CREATE TABLE inventory_items (
    id SERIAL PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
    item_type item_type NOT NULL,
    sku VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    default_sale_price NUMERIC(15,2),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_inventory_ledger_sku UNIQUE (ledger_id, sku)
);

-- Inventory Layers
CREATE TABLE inventory_layers (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    journal_entry_id INTEGER REFERENCES journal_entries(id),
    quantity_purchased NUMERIC(15,4) NOT NULL,
    quantity_remaining NUMERIC(15,4) NOT NULL,
    unit_cost NUMERIC(15,4) NOT NULL,
    received_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_accounts_ledger ON accounts(ledger_id);
CREATE INDEX idx_journal_entries_ledger_date ON journal_entries(ledger_id, date);
CREATE INDEX idx_journal_lines_entry ON journal_lines(journal_entry_id);
CREATE INDEX idx_journal_lines_account ON journal_lines(account_id);
CREATE INDEX idx_inventory_items_ledger ON inventory_items(ledger_id);
CREATE INDEX idx_inventory_layers_item ON inventory_layers(item_id);
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_accounting_models.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add auth/accounting_models.py migrations/add_accounting_tables.sql tests/test_accounting_models.py
git commit -m "feat: add accounting database models and migration"
```

---

## Task 3: DB Test Fixtures + Internal Primitives

**Files:**
- Modify: `tests/conftest.py`
- Create: `tools/accounting.py` (initial — primitives + helpers only)

- [ ] **Step 1: Add accounting fixtures to conftest.py**

Append to `tests/conftest.py`:

```python
import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from auth.models import Base
from auth.accounting_models import (
    Ledger, Account, AccountType, NormalBalance, NORMAL_BALANCE_MAP,
    JournalEntry, JournalLine, InventoryItem, InventoryLayer,
    ItemType, SourceType,
)

TEST_DB_URL = "postgresql://agentic:agentic_dev@localhost:5432/agentic_test"

@pytest.fixture(scope="session")
def accounting_engine():
    """Create test DB tables once per test session."""
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(accounting_engine):
    """Per-test DB session that rolls back after each test."""
    conn = accounting_engine.connect()
    trans = conn.begin()
    session = Session(bind=conn)
    yield session
    session.close()
    trans.rollback()
    conn.close()

@pytest.fixture
def ledger_with_defaults(db_session):
    """A ledger with the standard default accounts."""
    from tools.accounting import _create_default_accounts
    ledger = Ledger(user_id="test-user-001", name="Test Ledger")
    db_session.add(ledger)
    db_session.flush()
    _create_default_accounts(db_session, ledger.id)
    db_session.flush()
    return ledger
```

- [ ] **Step 2: Write tests for internal primitives**

```python
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
```

- [ ] **Step 3: Run tests — expect failure**

Run: `.venv/bin/python -m pytest tests/test_accounting_primitives.py -v`

- [ ] **Step 4: Implement the initial `tools/accounting.py`**

This step creates the file with helpers and primitives only — no @tool functions yet.

```python
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
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_accounting_primitives.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add tools/accounting.py tests/test_accounting_primitives.py tests/conftest.py
git commit -m "feat: add accounting primitives, helpers, and default accounts"
```

---

## Task 4: Ledger + Account Tools (5 tools)

**Files:**
- Modify: `tools/accounting.py`
- Test: `tests/test_accounting_ledger.py`

Tools: `create_ledger`, `create_account`, `list_accounts`, `get_account_balance`, `update_account`

- [ ] **Step 1: Write tests**

```python
# tests/test_accounting_ledger.py
"""Test ledger setup and account management tools."""
import json
import pytest


def test_create_ledger(db_session):
    from tools.accounting import _create_ledger_impl
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `.venv/bin/python -m pytest tests/test_accounting_ledger.py -v`

- [ ] **Step 3: Implement the 5 tools**

Add to `tools/accounting.py` (after the primitives section):

```python
from langchain.tools import tool


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
```

Update the `ACCOUNTING_TOOLS` list at the bottom:

```python
ACCOUNTING_TOOLS = [
    create_ledger,
    create_account,
    list_accounts,
    get_account_balance,
    update_account,
]
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_accounting_ledger.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add tools/accounting.py tests/test_accounting_ledger.py tests/conftest.py
git commit -m "feat: add ledger setup and account management tools (5 of 21)"
```

---

## Task 5: Journal Entry Tools (4 tools)

**Files:**
- Modify: `tools/accounting.py`
- Test: `tests/test_accounting_journal.py`

Tools: `journalize_transaction`, `search_journal`, `void_transaction`, `account_ledger`

- [ ] **Step 1: Write tests**

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `.venv/bin/python -m pytest tests/test_accounting_journal.py -v`

- [ ] **Step 3: Implement the 4 tools**

Add `_journalize_transaction_impl`, `_search_journal_impl`, `_void_transaction_impl`, `_account_ledger_impl` and their `@tool` wrappers to `tools/accounting.py`. Each `_impl` function takes a `db` session and `user_id` (for testability). The `@tool` wrapper gets `current_user.id` from Flask and manages the session.

Key implementation details for `_journalize_transaction_impl`:
```python
def _journalize_transaction_impl(db, user_id, date_str, memo, lines):
    # 1. Validate ledger exists
    # 2. Parse date
    # 3. Validate each line: account exists, debit XOR credit, amounts positive
    # 4. Sum debits and credits, reject if not equal
    # 5. Create JournalEntry with source_type=MANUAL
    # 6. For each line, dispatch to _PRIMITIVE_DISPATCH[(account.account_type, side)]
    # 7. Return entry id + line details
```

Key implementation details for `_void_transaction_impl`:
```python
def _void_transaction_impl(db, user_id, entry_id, date_str, memo):
    # 1. Load original entry, verify it belongs to user's ledger
    # 2. Reject if is_void == True
    # 3. Reject if void_of_id is not None (it's a reversal)
    # 4. Create new JournalEntry with source_type=VOID, void_of_id=original.id
    # 5. For each original line, create opposite line (swap debit/credit)
    # 6. If original.source_type in (FIFO_SALE, LIFO_SALE): restore inventory layers
    # 7. If original.source_type == INVENTORY_RECEIPT: set layer quantity_remaining to 0
    # 8. Mark original is_void = True
    # 9. Return reversal entry id
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_accounting_journal.py -v`
Expected: 11 passed

- [ ] **Step 5: Update ACCOUNTING_TOOLS list**

```python
ACCOUNTING_TOOLS = [
    create_ledger, create_account, list_accounts, get_account_balance, update_account,
    journalize_transaction, search_journal, void_transaction, account_ledger,
]
```

- [ ] **Step 6: Commit**

```bash
git add tools/accounting.py tests/test_accounting_journal.py
git commit -m "feat: add journal entry, search, void, and account ledger tools (9 of 21)"
```

---

## Task 6: Inventory Tools (4 tools)

**Files:**
- Modify: `tools/accounting.py`
- Test: `tests/test_accounting_inventory.py`

Tools: `register_inventory_item`, `receive_inventory`, `list_inventory_items`, `deactivate_inventory_item`

- [ ] **Step 1: Write tests**

```python
# tests/test_accounting_inventory.py
"""Test inventory registration, receiving, and listing."""
import json
import pytest


def test_register_item(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl
    result = json.loads(_register_inventory_item_impl(
        db_session, "test-user-001", "WDG-001", "Widget", "goods", 29.99
    ))
    assert result["status"] == "success"
    assert result["data"]["sku"] == "WDG-001"


def test_register_duplicate_sku(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl
    _register_inventory_item_impl(db_session, "test-user-001", "WDG-001", "Widget", "goods")
    db_session.flush()
    result = json.loads(_register_inventory_item_impl(
        db_session, "test-user-001", "WDG-001", "Duplicate", "goods"
    ))
    assert result["status"] == "error"
    assert "already exists" in result["error"].lower()


def test_receive_inventory(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl, _receive_inventory_impl, _get_account_balance_impl
    _register_inventory_item_impl(db_session, "test-user-001", "WDG-001", "Widget", "goods")
    db_session.flush()

    result = json.loads(_receive_inventory_impl(
        db_session, "test-user-001", "WDG-001", 100, 5.00, "2026-03-20", "Cash"
    ))
    assert result["status"] == "success"
    assert result["data"]["layer"]["quantity_purchased"] == "100"
    assert result["data"]["journal_entry_id"] is not None

    # Verify accounting: Inventory debited, Cash credited
    inv_bal = json.loads(_get_account_balance_impl(db_session, "test-user-001", "Inventory"))
    cash_bal = json.loads(_get_account_balance_impl(db_session, "test-user-001", "Cash"))
    assert float(inv_bal["data"]["balance"]) == 500.00
    assert float(cash_bal["data"]["balance"]) == -500.00


def test_list_inventory(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl, _receive_inventory_impl, _list_inventory_items_impl
    _register_inventory_item_impl(db_session, "test-user-001", "WDG-001", "Widget", "goods")
    db_session.flush()
    _receive_inventory_impl(db_session, "test-user-001", "WDG-001", 50, 5.00, "2026-03-20", "Cash")
    db_session.flush()

    result = json.loads(_list_inventory_items_impl(db_session, "test-user-001"))
    assert result["status"] == "success"
    assert len(result["data"]["items"]) == 1
    assert float(result["data"]["items"][0]["quantity_on_hand"]) == 50


def test_deactivate_inventory_item(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl, _deactivate_inventory_item_impl
    _register_inventory_item_impl(db_session, "test-user-001", "SVC-001", "Consulting", "service")
    db_session.flush()

    result = json.loads(_deactivate_inventory_item_impl(db_session, "test-user-001", "SVC-001"))
    assert result["status"] == "success"
    assert result["data"]["is_active"] is False


def test_deactivate_with_remaining_inventory(db_session, ledger_with_defaults):
    from tools.accounting import _register_inventory_item_impl, _receive_inventory_impl, _deactivate_inventory_item_impl
    _register_inventory_item_impl(db_session, "test-user-001", "WDG-001", "Widget", "goods")
    db_session.flush()
    _receive_inventory_impl(db_session, "test-user-001", "WDG-001", 10, 5.00, "2026-03-20", "Cash")
    db_session.flush()

    result = json.loads(_deactivate_inventory_item_impl(db_session, "test-user-001", "WDG-001"))
    assert result["status"] == "error"
    assert "quantity_remaining" in result["error"].lower() or "deplete" in result["error"].lower()
```

- [ ] **Step 2: Run tests — expect failure**

Run: `.venv/bin/python -m pytest tests/test_accounting_inventory.py -v`

- [ ] **Step 3: Implement the 4 tools**

Key for `_receive_inventory_impl`:
```python
# 1. Look up item by SKU
# 2. Create inventory layer
# 3. Auto-journal: debit Inventory, credit payment_account
#    via _journalize_transaction_impl with source_type=INVENTORY_RECEIPT
# 4. Link layer to journal entry via journal_entry_id
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_accounting_inventory.py -v`
Expected: 6 passed

- [ ] **Step 5: Update ACCOUNTING_TOOLS and commit**

```bash
git add tools/accounting.py tests/test_accounting_inventory.py
git commit -m "feat: add inventory registration and receiving tools (13 of 21)"
```

---

## Task 7: FIFO/LIFO + Inventory Valuation (3 tools)

**Files:**
- Modify: `tools/accounting.py`
- Test: `tests/test_accounting_fifo_lifo.py`

Tools: `journalize_fifo_transaction`, `journalize_lifo_transaction`, `inventory_valuation`

- [ ] **Step 1: Write tests**

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `.venv/bin/python -m pytest tests/test_accounting_fifo_lifo.py -v`

- [ ] **Step 3: Implement the 3 tools**

Key for `_journalize_fifo_transaction_impl`:
```python
# 1. Validate item exists, is goods (not service), has sufficient quantity
# 2. Pull layers ordered by received_date ASC (FIFO)
# 3. Consume layers: decrement quantity_remaining, accumulate COGS
# 4. Build journal lines:
#    - Debit "Cost of Goods Sold" / Credit "Inventory" (per layer, with layer memo)
#    - If sale_price: Debit receivable_account / Credit revenue_account
# 5. Create JournalEntry with source_type=FIFO_SALE
# 6. Return entry id, layers consumed, total COGS, sale total
```

LIFO is identical but orders layers by `received_date DESC`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_accounting_fifo_lifo.py -v`
Expected: 6 passed

- [ ] **Step 5: Update ACCOUNTING_TOOLS and commit**

```bash
git add tools/accounting.py tests/test_accounting_fifo_lifo.py
git commit -m "feat: add FIFO/LIFO costing and inventory valuation tools (16 of 21)"
```

---

## Task 8: Period Close + Reporting Tools (5 tools)

**Files:**
- Modify: `tools/accounting.py`
- Test: `tests/test_accounting_reporting.py`

Tools: `close_period`, `trial_balance`, `income_statement`, `balance_sheet`, `cash_flow_statement`

- [ ] **Step 1: Write tests**

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `.venv/bin/python -m pytest tests/test_accounting_reporting.py -v`

- [ ] **Step 3: Implement the 5 tools**

Key for `_close_period_impl`:
```python
# 1. Get all revenue accounts with non-zero balances
# 2. Get all expense accounts with non-zero balances
# 3. If both empty: return "nothing to close"
# 4. Entry 1: Debit each revenue account, Credit Income Summary
# 5. Entry 2: Credit each expense account, Debit Income Summary
# 6. Entry 3: Close Income Summary to Owner's Capital
# 7. All entries get source_type=PERIOD_CLOSE
```

Key for `_cash_flow_statement_impl`:
```python
# Indirect method:
# 1. Compute net income (revenue - expenses for period)
# 2. Operating: net income +/- changes in current assets (AR, Inventory) and liabilities (AP)
# 3. Investing: changes in long-term asset accounts (if any)
# 4. Financing: changes in equity accounts (excluding retained earnings from close)
# 5. Beginning cash = Cash balance at start_date
# 6. Ending cash = beginning + net change
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_accounting_reporting.py -v`
Expected: 6 passed

- [ ] **Step 5: Update ACCOUNTING_TOOLS and commit**

```bash
git add tools/accounting.py tests/test_accounting_reporting.py
git commit -m "feat: add period close and financial reporting tools (21 of 21)"
```

---

## Task 9: Integration — Tool Registry + tools_server.py

> **Note:** The `create_mcp_agent` pattern in `agents/` is not in use. Accounting tools are registered in `tools/__init__.py` (for the main Flask app) and exposed via `tools_server.py` (the only MCP server).

**Files:**
- Modify: `tools/__init__.py`
- Modify: `tools_server.py`
- Test: `tests/test_integration_accounting.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_integration_accounting.py
"""Test accounting tools are registered and accessible."""

def test_accounting_tools_in_registry():
    from tools import ALL_TOOLS
    names = {t.name for t in ALL_TOOLS}
    assert "create_ledger" in names
    assert "journalize_transaction" in names
    assert "trial_balance" in names
    assert "balance_sheet" in names

def test_accounting_tool_count():
    from tools.accounting import ACCOUNTING_TOOLS
    assert len(ACCOUNTING_TOOLS) == 21

def test_tools_server_lists_accounting():
    """tools_server.py Flask app should list accounting tools."""
    from tools_server import tools_app
    client = tools_app.test_client()
    resp = client.get("/")
    data = resp.get_json()
    assert "create_ledger" in data
    assert "journalize_transaction" in data
```

- [ ] **Step 2: Run tests — expect failure**

Run: `.venv/bin/python -m pytest tests/test_integration_accounting.py -v`

- [ ] **Step 3: Add to tools/__init__.py**

```python
from tools.accounting import ACCOUNTING_TOOLS
```

Add `+ ACCOUNTING_TOOLS` to the `ALL_TOOLS` concatenation.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_integration_accounting.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tools/__init__.py tests/test_integration_accounting.py
git commit -m "feat: register accounting tools in tool registry and tools_server"
```

---

## Task 10: Run Migration + Full Test Suite

- [ ] **Step 1: Run migration against dev database**

```bash
psql -U agentic -d agentic -f migrations/add_accounting_tables.sql
```

- [ ] **Step 2: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 3: Verify tool count**

```bash
.venv/bin/python -c "from tools import ALL_TOOLS; acct = [t for t in ALL_TOOLS if 'ledger' in t.name or 'journal' in t.name or 'account' in t.name or 'inventory' in t.name or 'trial' in t.name or 'income' in t.name or 'balance' in t.name or 'cash_flow' in t.name or 'close' in t.name or 'fifo' in t.name or 'lifo' in t.name or 'void' in t.name or 'valuation' in t.name]; print(f'{len(acct)} accounting tools'); print(f'{len(ALL_TOOLS)} total tools')"
```

Expected: `21 accounting tools`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: accounting tools module complete — 21 tools, 6 tables, full test coverage"
```

---

## Execution Order & Dependencies

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7 → Task 8 → Task 9 → Task 10
```

All tasks are strictly sequential — each builds on the previous.
