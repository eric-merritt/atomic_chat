"""SQLAlchemy models for conversations."""

from datetime import datetime, timezone

import os

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

# Use PostgreSQL's binary JSONB when available; fall back to generic JSON for SQLite
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgresql"):
    from sqlalchemy.dialects.postgresql import JSONB as _JsonType
else:
    _JsonType = JSON

from auth.models import Base, _uuid, _now


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False, default="New Conversation")
    folder = Column(String(128), nullable=True)
    model = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User")
    messages = relationship("ConversationMessage", back_populates="conversation",
                            cascade="all, delete-orphan", order_by="ConversationMessage.created_at")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False, default="")
    images = Column(_JsonType, nullable=False, default=list, server_default='[]')
    tool_calls = Column(_JsonType, nullable=False, default=list, server_default='[]')
    created_at = Column(DateTime(timezone=True), default=_now)

    conversation = relationship("Conversation", back_populates="messages")
