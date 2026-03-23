"""add conversation_tasks table

Revision ID: d43a6b2d16db
Revises: af34c6d3d40d
Create Date: 2026-03-23 12:41:48.647047

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd43a6b2d16db'
down_revision: Union[str, Sequence[str], None] = 'af34c6d3d40d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create conversation_tasks table."""
    op.create_table(
        'conversation_tasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('conversation_messages.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_conversation_tasks_conversation', 'conversation_tasks', ['conversation_id'])


def downgrade() -> None:
    """Drop conversation_tasks table."""
    op.drop_index('ix_conversation_tasks_conversation', table_name='conversation_tasks')
    op.drop_table('conversation_tasks')
