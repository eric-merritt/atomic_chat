"""add running_summary to conversation

Revision ID: e05a7ec1d7ca
Revises: 40ccd675e87f
Create Date: 2026-06-28

Backs inline context compaction: running_summary holds the folded gist of
messages older than the recent window; summary_covers_through marks the
created_at of the last message already folded in, so each compaction only
summarizes messages newer than that. Messages are never deleted.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e05a7ec1d7ca'
down_revision: Union[str, Sequence[str], None] = '40ccd675e87f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('running_summary', sa.Text(), nullable=True))
    op.add_column('conversations', sa.Column('summary_covers_through', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('conversations', 'summary_covers_through')
    op.drop_column('conversations', 'running_summary')
