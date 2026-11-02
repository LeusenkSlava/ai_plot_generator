"""Add roadmap prompt version 2: pass the user's original prompt

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-02 14:00:00.000000

Причина: роадмап строился только из LLM-описания новеллы
(title/description/tone), а исходный запрос пользователя (user_prompt) терялся —
детали и теги, которые LLM не перенёс в description, до роадмапа не доходили.
Добавляем {user_prompt} в user-шаблон, чтобы генератор роадмапа видел исходный
замысел. system-шаблон не меняется — копируем его из активной версии 1.
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


# user-шаблон версии 2: в начало добавлен исходный запрос пользователя.
_ROADMAP_USER = """User request: {user_prompt}

Title: {title}
Description: {description}
Narrative tone: {tone}{place_time_catalog}{characters_block}"""


def upgrade() -> None:
    """Upgrade schema: version 2 промпта roadmap, деактивация version 1."""
    now = datetime.now(UTC)
    # system-шаблон не меняется — переносим его из активной version 1 как есть.
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

    # Деактивируем version 1 для переизданного ключа (по обоим вариантам).
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
