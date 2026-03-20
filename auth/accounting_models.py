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
