"""add notified_at to conversation_tasks

Revision ID: 4e2a9f7bd011
Revises: 80923e8fefe3
Create Date: 2026-04-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4e2a9f7bd011'
down_revision: Union[str, Sequence[str], None] = '80923e8fefe3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'conversation_tasks',
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversation_tasks', 'notified_at')
