"""Pytest configuration — ensure project root is on sys.path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from auth.models import Base, User
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
def test_user(db_session):
    """A test user for accounting fixtures."""
    user = User(id="test-user-001", username="testuser", auth_method="local")
    db_session.add(user)
    db_session.flush()
    return user

@pytest.fixture
def ledger_with_defaults(db_session, test_user):
    """A ledger with the standard default accounts."""
    from tools.accounting import _create_default_accounts
    ledger = Ledger(user_id=test_user.id, name="Test Ledger")
    db_session.add(ledger)
    db_session.flush()
    _create_default_accounts(db_session, ledger.id)
    db_session.flush()
    return ledger
