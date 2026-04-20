"""SQLAlchemy model for conversation-scoped tasks.

These tasks are ephemeral pipeline artifacts created by the Task Extractor
and consumed by the Tool Curator. They die with the conversation.

When the PM workflow lands, conversation tasks can be promoted to
project_tasks via a one-way copy with a promoted_from FK.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from auth.models import Base, _uuid, _now


class ConversationTask(Base):
    __tablename__ = "conversation_tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    conversation_id = Column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id = Column(
        String(36),
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    depends_on = Column(
        String(36),
        ForeignKey("conversation_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), default=_now)
    notified_at = Column(DateTime(timezone=True), nullable=True)

    conversation = relationship("Conversation")
    dependency = relationship("ConversationTask", remote_side="ConversationTask.id")
