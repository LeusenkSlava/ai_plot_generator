"""Диалог: фон сцены задаётся одним top-level полем, а не на каждую реплику

Revision ID: 9b1c2d3e4f5a
Revises: 9a0b1c2d3e4f
Create Date: 2026-11-04 20:05:00.000000

Причина: фон сцены резолвился на каждую реплику из тегов, которые модель выбирала
по строке, — отсюда «скачки» локации и фликер модификаторов. Теперь генератор
резолвит фон один раз на сцену (база = scenes.location_slug, модификаторы — из
одного поля ответа), а модель больше не выбирает фон построчно.

Изменение JSON-схемы диалога (все активные варианты): в корень ответа добавляется
``background_modifier_tags``, а поля ``background_base_tag``/``background_modifier_tags``
из описания реплик убираются (инструкции живут в коде — ``assets_block``).

Схема общая для всех вариантов, поэтому замена делается строковой правкой
идентичного JSON-блока. Каждая правка публикуется новой версией (append-only),
старые версии гасятся. Миграция идемпотентна: вариант с уже заменённой схемой
пропускается.
"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b1c2d3e4f5a'
down_revision: Union[str, Sequence[str], None] = '9a0b1c2d3e4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Точный JSON-блок схемы во всех активных шаблонах диалога (2 пробела отступа).
_SCHEMA_OLD = (
    "{\n"
    '  "dialogue_lines": [\n'
    '    { "kind": string, "character_name": string|null, "text": string }\n'
    "  ]\n"
    "}"
)

_SCHEMA_NEW = (
    "{\n"
    '  "background_modifier_tags": [string],\n'
    '  "dialogue_lines": [\n'
    '    { "kind": string, "character_name": string|null, "text": string }\n'
    "  ]\n"
    "}"
)


def _dialogue_active(bind: sa.Connection) -> list[dict]:
    """(key, variant, version, system, user) всех активных шаблонов диалога."""
    rows = bind.execute(
        sa.text(
            "SELECT variant, version, system_template, user_template "
            "FROM prompts WHERE key = 'dialogue' AND is_active ORDER BY variant"
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _next_version(bind: sa.Connection, variant: str) -> int:
    return bind.execute(
        sa.text(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM prompts "
            "WHERE key = 'dialogue' AND variant = :variant"
        ),
        {"variant": variant},
    ).scalar_one()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    now = datetime.now(UTC)

    for row in _dialogue_active(bind):
        variant = row["variant"]
        system = row["system_template"]
        if _SCHEMA_NEW in system:
            # Уже мигрирован — пропускаем.
            continue
        if _SCHEMA_OLD not in system:
            raise RuntimeError(
                f"dialogue/{variant}: schema block not found — prompt drift, "
                "update _SCHEMA_OLD in this migration"
            )
        new_system = system.replace(_SCHEMA_OLD, _SCHEMA_NEW, 1)
        version = _next_version(bind, variant)
        bind.execute(
            sa.text(
                "INSERT INTO prompts "
                "(key, variant, version, system_template, user_template, is_active, "
                "created_at, updated_at) "
                "VALUES ('dialogue', :variant, :version, :system, :user, true, :now, :now)"
            ),
            {
                "variant": variant,
                "version": version,
                "system": new_system,
                "user": row["user_template"],
                "now": now,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE prompts SET is_active = false, updated_at = :now "
                "WHERE key = 'dialogue' AND variant = :variant AND version <> :version"
            ),
            {"variant": variant, "version": version, "now": now},
        )

    # Контроль целостности: у каждой пары (key, variant) ровно одна активная строка.
    broken = bind.execute(
        sa.text(
            "SELECT variant FROM prompts WHERE key = 'dialogue' "
            "GROUP BY variant HAVING COUNT(*) FILTER (WHERE is_active) <> 1 "
            "ORDER BY variant"
        )
    ).scalars().all()
    if broken:
        raise RuntimeError(
            "dialogue prompts: expected exactly 1 active row per variant, "
            f"broken variants: {', '.join(broken)}"
        )


def downgrade() -> None:
    """Downgrade schema: удалить новые версии, вернуть is_active предыдущей."""
    bind = op.get_bind()
    now = datetime.now(UTC)

    for row in _dialogue_active(bind):
        variant = row["variant"]
        # Удаляем только строки с новой схемой (top-level background_modifier_tags).
        bind.execute(
            sa.text(
                "DELETE FROM prompts WHERE key = 'dialogue' AND variant = :variant "
                "AND system_template LIKE :needle"
            ),
            {"variant": variant, "needle": '%"background_modifier_tags": [string],%'},
        )
        # Возвращаем активность самой свежей оставшейся версии.
        bind.execute(
            sa.text(
                "UPDATE prompts SET is_active = true, updated_at = :now "
                "WHERE key = 'dialogue' AND variant = :variant AND version = ("
                "  SELECT MAX(version) FROM prompts "
                "  WHERE key = 'dialogue' AND variant = :variant"
                ")"
            ),
            {"variant": variant, "now": now},
        )
