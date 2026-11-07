"""Публикация новелл: ``novels.is_published`` и ``novels.published_at``

Revision ID: b7c8d9e0f1a2
Revises: a1c2e3f4b5d6
Create Date: 2026-11-07 13:00:00.000000

Опубликованная новелла становится доступна всем читателям, в том числе
неавторизованным: шлюз ``my_choice_api`` не передаёт ``X-User-Id`` для
анонимных запросов, а этот сервис отдаёт им только ``is_published = true``.
Публикует новеллу только её автор.

Существующие новеллы остаются неопубликованными (``false``): публикация —
осознанное действие автора. ``published_at`` заполняется в момент публикации
и очищается при снятии с публикации.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1c2e3f4b5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "novels",
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "novels",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_novels_is_published", "novels", ["is_published"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_novels_is_published", table_name="novels")
    op.drop_column("novels", "published_at")
    op.drop_column("novels", "is_published")
