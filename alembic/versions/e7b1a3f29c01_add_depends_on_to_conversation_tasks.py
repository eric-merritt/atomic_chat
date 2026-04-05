"""add depends_on to conversation_tasks

Revision ID: e7b1a3f29c01
Revises: d43a6b2d16db
Create Date: 2026-03-23 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7b1a3f29c01'
down_revision: Union[str, Sequence[str], None] = 'd43a6b2d16db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add depends_on self-referential FK to conversation_tasks."""
    op.add_column(
        'conversation_tasks',
        sa.Column('depends_on', sa.String(36), sa.ForeignKey('conversation_tasks.id', ondelete='SET NULL'), nullable=True),
    )


def downgrade() -> None:
    """Remove depends_on from conversation_tasks."""
    op.drop_column('conversation_tasks', 'depends_on')
