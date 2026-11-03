"""Промпт roadmap version 2: в user-шаблон передаётся исходный запрос пользователя

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-02 14:00:00.000000

Предпосылка: roadmap строился только из LLM-описания новеллы (title/description/
tone). Исходный user_prompt в промпт не передавался, поэтому его детали и теги,
не перенесённые в description, до роадмапа не доходили.

Изменения в version 2 (ключ roadmap):
- в начало user-шаблона добавляется плейсхолдер {user_prompt};
- system-шаблон не меняется: при вставке копируется из активной version 1.
"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# user-шаблон version 2: {user_prompt} первым полем.
_ROADMAP_USER = """User request: {user_prompt}

Title: {title}
Description: {description}
Narrative tone: {tone}{place_time_catalog}{characters_block}"""


def upgrade() -> None:
    """Upgrade schema: version 2 промпта roadmap, деактивация version 1."""
    now = datetime.now(UTC)
    # system-шаблон берётся из активной version 1 без изменений (INSERT ... SELECT).
    op.execute(
        sa.text(
            """
            INSERT INTO prompts
                (key, variant, version, system_template, user_template, is_active, created_at, updated_at)
            SELECT key, variant, 2, system_template, :user_template, true, :now, :now
            FROM prompts
            WHERE key = 'roadmap' AND version = 1 AND is_active
            """
        ).bindparams(user_template=_ROADMAP_USER, now=now)
    )

    # Деактивация version 1 ключа roadmap в обоих вариантах (default, nsfw).
    op.execute(
        sa.text(
            "UPDATE prompts SET is_active = false "
            "WHERE key = 'roadmap' AND version = 1"
        )
    )


def downgrade() -> None:
    """Downgrade schema: вернуть активность version 1 и убрать version 2."""
    op.execute(sa.text("DELETE FROM prompts WHERE key = 'roadmap' AND version = 2"))
    op.execute(
        sa.text(
            "UPDATE prompts SET is_active = true "
            "WHERE key = 'roadmap' AND version = 1"
        )
    )
