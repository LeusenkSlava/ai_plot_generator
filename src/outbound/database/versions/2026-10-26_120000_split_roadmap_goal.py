"""Split roadmap goal into event/conflict/change

Revision ID: b7e4d9f0c3a6
Revises: a3f9c1d7e2b4
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e4d9f0c3a6'
down_revision: Union[str, Sequence[str], None] = 'a3f9c1d7e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Единую расплывчатую цель шага разбиваем на три оси, чтобы сцена и валидатор
    # получали чёткий эталон: что происходит (event), что мешает (conflict),
    # что меняется для героя (change). DEFAULT '' сохранён намеренно: пустая строка
    # в этих полях означает «не задано» и не требует отдельного NULL-состояния.
    op.add_column('roadmap', sa.Column('event', sa.String(), nullable=False, server_default=''))
    op.add_column('roadmap', sa.Column('conflict', sa.String(), nullable=False, server_default=''))
    op.add_column('roadmap', sa.Column('change', sa.String(), nullable=False, server_default=''))
    # Существующие строки: старый goal сохраняем как событие.
    op.execute("UPDATE roadmap SET event = goal")
    op.drop_column('roadmap', 'goal')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('roadmap', sa.Column('goal', sa.String(), nullable=False, server_default=''))
    op.execute("UPDATE roadmap SET goal = event")
    op.drop_column('roadmap', 'change')
    op.drop_column('roadmap', 'conflict')
    op.drop_column('roadmap', 'event')
