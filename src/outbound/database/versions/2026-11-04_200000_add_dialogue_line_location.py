"""Добавлено dialogue_lines.location_slug — локация реплики для блока «Last lines»

Revision ID: 9a0b1c2d3e4f
Revises: f4e5d6c7b8a9
Create Date: 2026-11-04 20:00:00.000000

Фон сцены теперь резолвится один раз и раздаётся всем репликам (см. генератор
диалога), поэтому базовую локацию реплики можно хранить прямо на строке. Это нужно
блоку «Last lines of the previous scene» промпта диалога: каждая прошлая реплика
передаётся вместе с тегом локации, где она происходит, чтобы модель не путала
места между сценами.

Существующие строки бэкфиллятся из scenes.location_slug (авторитетное место сцены).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a0b1c2d3e4f'
down_revision: Union[str, Sequence[str], None] = 'f4e5d6c7b8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'dialogue_lines',
        sa.Column('location_slug', sa.String(), nullable=True),
    )

    # Бэкфилл: локация реплики наследуется от локации её сцены.
    op.execute(
        """
        UPDATE dialogue_lines
        SET location_slug = scenes.location_slug
        FROM scenes
        WHERE scenes.id = dialogue_lines.scene_id
          AND dialogue_lines.location_slug IS NULL
          AND scenes.location_slug IS NOT NULL
          AND scenes.location_slug <> ''
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dialogue_lines', 'location_slug')
