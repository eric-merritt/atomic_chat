"""Token usage tracking."""

import uuid
from datetime import datetime, timezone, date

from sqlalchemy import Column, String, Integer, DateTime, func

from auth.models import Base
from auth.db import SessionLocal

DAILY_FREE_LIMIT = 10_000_000  # effectively unlimited for local dev
WARN_THRESHOLD   = 0.75   # show bar at 75%


def _uuid() -> str:
    return str(uuid.uuid4())

def _now() -> datetime:
    return datetime.now(timezone.utc)


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id               = Column(String(36), primary_key=True, default=_uuid)
    user_id          = Column(String(36), nullable=False, index=True)
    conversation_id  = Column(String(36), nullable=True)
    model            = Column(String(128), nullable=True)
    prompt_tokens    = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    created_at       = Column(DateTime(timezone=True), default=_now, index=True)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


def record_usage(
    user_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    conversation_id: str | None = None,
    model: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        db.add(UsageEvent(
            user_id=user_id,
            conversation_id=conversation_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ))
        db.commit()
    finally:
        db.close()


def get_daily_usage(user_id: str) -> int:
    """Return total tokens used today (UTC) for this user."""
    db = SessionLocal()
    try:
        today = date.today()
        total = db.query(
            func.coalesce(
                func.sum(UsageEvent.prompt_tokens + UsageEvent.completion_tokens), 0
            )
        ).filter(
            UsageEvent.user_id == user_id,
            func.date(UsageEvent.created_at) == today,
        ).scalar()
        return int(total)
    finally:
        db.close()


def quota_status(user_id: str, limit: int = DAILY_FREE_LIMIT) -> dict:
    """Return usage dict: used, limit, percent (0-100), warn (bool), exhausted (bool)."""
    used    = get_daily_usage(user_id)
    percent = min(100, round(used / limit * 100))
    return {
        "used":      used,
        "limit":     limit,
        "percent":   percent,
        "warn":      percent >= int(WARN_THRESHOLD * 100),
        "exhausted": used >= limit,
    }
