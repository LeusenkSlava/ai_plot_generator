"""Add protagonist and thoughts

Revision ID: 7b3d5e8f9a1c
Revises: 8d4f9a6cf3a1
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b3d5e8f9a1c'
down_revision: Union[str, Sequence[str], None] = '8d4f9a6cf3a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # is_protagonist: главный герой/героиня (без спрайта, доступны мысли).
    # server_default для существующих строк, дальше значение задаёт приложение.
    op.add_column(
        'characters',
        sa.Column('is_protagonist', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # is_thought: реплика-внутренние мысли (значимо для протагониста).
    op.add_column(
        'dialogue_lines',
        sa.Column('is_thought', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dialogue_lines', 'is_thought')
    op.drop_column('characters', 'is_protagonist')
