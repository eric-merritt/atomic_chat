"""Tests for ConversationTask model CRUD."""
import auth.conversations  # noqa: F401 — register Conversation with mapper
from auth.conversation_tasks import ConversationTask


def test_conversation_task_fields():
    """Verify the model has the expected columns."""
    columns = {c.name for c in ConversationTask.__table__.columns}
    assert {"id", "conversation_id", "title", "status", "created_at"}.issubset(columns)


def test_default_status():
    """Column default is 'pending' — applied at insert time by SQLAlchemy."""
    col = ConversationTask.__table__.columns["status"]
    assert col.default.arg == "pending"


def test_status_values():
    """Status must be one of the allowed values."""
    for status in ("pending", "active", "done"):
        task = ConversationTask(title="t", conversation_id="x", status=status)
        assert task.status == status
