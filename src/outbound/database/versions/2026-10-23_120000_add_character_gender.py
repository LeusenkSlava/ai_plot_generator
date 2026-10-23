"""Add character gender

Revision ID: a3f9c1d7e2b4
Revises: e9f3c7d2b5a1
Create Date: 2026-10-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c1d7e2b4'
down_revision: Union[str, Sequence[str], None] = 'e9f3c7d2b5a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # gender: пол персонажа из Codex; nullable — для персонажей без вселенной/маппинга.
    op.add_column(
        'characters',
        sa.Column('gender', sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('characters', 'gender')
