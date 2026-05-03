"""Database engine and session management."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from auth.models import Base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://agentic:agentic_dev@localhost:5432/agentic",
)

# Pool sizing — tuned for a single Flask worker with NDJSON streaming.
# Each chat stream holds a session for the duration of the response, so
# overflow headroom matters more than steady-state pool size. Override
# via env vars when scaling out (e.g. behind gunicorn with multiple workers).
_DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "10"))
_DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "20"))
_DB_POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "1800"))  # 30 min
_DB_POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=_DB_POOL_SIZE,
        max_overflow=_DB_MAX_OVERFLOW,
        pool_recycle=_DB_POOL_RECYCLE,
        pool_timeout=_DB_POOL_TIMEOUT,
    )
SessionLocal = scoped_session(sessionmaker(bind=engine))


def init_db():
    """Create all tables (for dev — use Alembic in production)."""
    Base.metadata.create_all(engine)


def get_db():
    """Get a database session."""
    return SessionLocal()
