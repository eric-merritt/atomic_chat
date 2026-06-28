"""merge heads

Revision ID: 40ccd675e87f
Revises: a1b2c3d4e5f6, b9f2e4a1c703
Create Date: 2026-06-28 08:46:36.363553

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40ccd675e87f'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'b9f2e4a1c703')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
