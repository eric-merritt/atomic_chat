"""add action and expected_output to conversation_tasks

Revision ID: b9f2e4a1c703
Revises: e7b1a3f29c01
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b9f2e4a1c703'
down_revision: Union[str, Sequence[str], None] = 'e7b1a3f29c01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversation_tasks', sa.Column('action', sa.Text, nullable=True))
    op.add_column('conversation_tasks', sa.Column('expected_output', sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column('conversation_tasks', 'expected_output')
    op.drop_column('conversation_tasks', 'action')
