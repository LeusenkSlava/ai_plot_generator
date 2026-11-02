"""Add dialogue_lines.outfit_tag — style-тег наряда для блока «Current outfits»

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-02 21:00:00.000000

Каталог нарядов теперь приходит из Codex уже сгруппированным по style-тегу, и
обратный маппинг «asset_key картинки -> style-тег» больше не нужен. Вместо него
генератор сохраняет style-тег (`outfit_tag`), который он и так передал в
``match_visual``, — из него собирается блок «Current character outfits».
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
    op.add_column(
        'dialogue_lines',
        sa.Column('outfit_tag', sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dialogue_lines', 'outfit_tag')
