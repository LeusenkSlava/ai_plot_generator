"""Добавлено dialogue_lines.outfit_tag — style-тег наряда для блока «Current outfits»

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-02 21:00:00.000000

Каталог нарядов из Codex приходит сгруппированным по style-тегу; обратный маппинг
«asset_key картинки -> style-тег» больше не нужен. Генератор сохраняет style-тег
(``outfit_tag``), который передаёт в ``match_visual``; из него собирается блок
«Current character outfits» промпта диалога.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # outfit_tag: style-тег наряда персонажа на момент реплики; NULL — наряд не задан.
    op.add_column(
        'dialogue_lines',
        sa.Column('outfit_tag', sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dialogue_lines', 'outfit_tag')
