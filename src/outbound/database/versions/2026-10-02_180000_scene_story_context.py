"""scenes.story_context: изложение истории после сцены

Revision ID: 5d2f8c6a1e47
Revises: 7a3e9b1d4c20
Create Date: 2026-10-02 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d2f8c6a1e47'
down_revision: Union[str, Sequence[str], None] = '7a3e9b1d4c20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('scenes', sa.Column('story_context', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scenes', 'story_context')
