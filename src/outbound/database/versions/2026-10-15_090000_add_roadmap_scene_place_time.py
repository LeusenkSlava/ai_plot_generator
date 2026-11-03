"""Добавлены location_slug, time_of_day, day в roadmap и scenes

Revision ID: e9f3c7d2b5a1
Revises: d4e8b2c0a3f6
Create Date: 2026-10-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9f3c7d2b5a1'
down_revision: Union[str, Sequence[str], None] = 'd4e8b2c0a3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # location_slug / time_of_day / day: шаг роадмапа задаёт место и время действия,
    # сцена наследует значения. Валидатор сверяет сцену с шагом по этим полям.
    for table in ('roadmap', 'scenes'):
        op.add_column(table, sa.Column('location_slug', sa.String(), nullable=True))
        op.add_column(table, sa.Column('time_of_day', sa.String(), nullable=True))
        op.add_column(table, sa.Column('day', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('roadmap', 'scenes'):
        op.drop_column(table, 'day')
        op.drop_column(table, 'time_of_day')
        op.drop_column(table, 'location_slug')
