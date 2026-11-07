"""Автор новеллы: ``novels.author_id`` (opaque id пользователя my_choice_api)

Revision ID: a1c2e3f4b5d6
Revises: c5d6e7f8a9b0
Create Date: 2026-11-07 12:00:00.000000

Причина: библиотека становится персональной. Пользователи и JWT живут в
``my_choice_api``; этот сервис хранит только ``author_id`` — целочисленный id
учётки, полученный от шлюза (HTTP-заголовок ``X-User-Id`` или поле
``author_id`` Kafka-команды). Паролей/email здесь нет.

Колонка nullable как защита от старых сообщений в топике и незавершённых
генераций: новые новеллы всегда создаются с автором. Существующие строки
привязываются к служебной учётке ``id = 1`` (``is_system = true`` в
``my_choice_api``): обычным пользователям они не видны, потому что выборка
фильтруется по ``author_id``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c2e3f4b5d6'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# id служебной учётки-«владельца» старых новелл (см. my_choice_api, seed users).
SYSTEM_AUTHOR_ID = 1


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "novels",
        sa.Column("author_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_novels_author_id", "novels", ["author_id"])
    # Backfill: всё, что было до авторства, принадлежит системной учётке.
    op.execute(
        sa.text(
            "UPDATE novels SET author_id = :author_id WHERE author_id IS NULL"
        ).bindparams(author_id=SYSTEM_AUTHOR_ID)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_novels_author_id", table_name="novels")
    op.drop_column("novels", "author_id")
