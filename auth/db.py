"""Database engine and session management."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from auth.models import Base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://agentic:agentic_dev@localhost:5432/agentic",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(bind=engine))


def init_db():
    """Create all tables (for dev — use Alembic in production)."""
    Base.metadata.create_all(engine)


def get_db():
    """Get a database session."""
    return SessionLocal()
