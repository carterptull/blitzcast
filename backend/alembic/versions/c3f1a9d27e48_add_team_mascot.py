"""add team mascot

Revision ID: c3f1a9d27e48
Revises: b796306930f9
Create Date: 2026-10-01 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f1a9d27e48'
down_revision: Union[str, Sequence[str], None] = 'b796306930f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('teams', sa.Column('mascot', sa.String(length=40), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('teams', 'mascot')
