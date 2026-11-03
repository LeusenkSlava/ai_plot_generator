"""Добавлено scenes.character_ids (ARRAY(Integer))

Revision ID: d4e8b2c0a3f6
Revises: c3f7a1b9d2e5
Create Date: 2026-10-14 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4e8b2c0a3f6'
down_revision: Union[str, Sequence[str], None] = 'c3f7a1b9d2e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # character_ids: id персонажей сцены. Заполняет SceneGenerator; DialogueGenerator
    # получает этот список вместо полного каста новеллы.
    op.add_column(
        'scenes',
        sa.Column('character_ids', postgresql.ARRAY(sa.Integer()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scenes', 'character_ids')
