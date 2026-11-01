"""Add dialogue_lines.kind (speech/thought/narration); character_id nullable

Revision ID: a1b2c3d4e5f6
Revises: f1e2d3c4b5a6
Create Date: 2026-11-01 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1e2d3c4b5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. kind — тип реплики (speech/thought/narration). VARCHAR + CHECK, как novels.mode.
    op.add_column(
        'dialogue_lines',
        sa.Column(
            'kind',
            sa.Enum(
                'speech', 'thought', 'narration',
                name='linekind', native_enum=False, length=32,
            ),
            nullable=False,
            server_default='speech',
        ),
    )

    # 2. Backfill: is_thought -> kind='thought'.
    op.execute("UPDATE dialogue_lines SET kind='thought' WHERE is_thought")

    # 3. character_id становится необязательным (NULL только для kind='narration').
    op.alter_column('dialogue_lines', 'character_id', nullable=True)

    # 4. is_thought больше не нужен — источник истины kind.
    op.drop_column('dialogue_lines', 'is_thought')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'dialogue_lines',
        sa.Column('is_thought', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE dialogue_lines SET is_thought=true WHERE kind='thought'")
    # Narration-строки (character_id IS NULL) мешают вернуть NOT NULL; на downgrade
    # остаётся nullable — полная обратимость здесь не гарантируется.
    op.alter_column('dialogue_lines', 'character_id', nullable=False)
    op.drop_column('dialogue_lines', 'kind')
