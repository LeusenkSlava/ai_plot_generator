"""roadmap.goal заменён на event/conflict/change

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
    # Цель шага разбита на три оси — эталон для генерации и валидации сцены:
    # event — что происходит, conflict — что этому мешает, change — что меняется
    # у протагониста к концу шага.
    # server_default='' намеренно: пустая строка трактуется как «не задано»,
    # отдельное NULL-состояние не требуется, колонка остаётся NOT NULL.
    op.add_column('roadmap', sa.Column('event', sa.String(), nullable=False, server_default=''))
    op.add_column('roadmap', sa.Column('conflict', sa.String(), nullable=False, server_default=''))
    op.add_column('roadmap', sa.Column('change', sa.String(), nullable=False, server_default=''))
    # Бэкфилл: значение прежнего goal переносится в event.
    op.execute("UPDATE roadmap SET event = goal")
    op.drop_column('roadmap', 'goal')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('roadmap', sa.Column('goal', sa.String(), nullable=False, server_default=''))
    op.execute("UPDATE roadmap SET goal = event")
    op.drop_column('roadmap', 'change')
    op.drop_column('roadmap', 'conflict')
    op.drop_column('roadmap', 'event')
