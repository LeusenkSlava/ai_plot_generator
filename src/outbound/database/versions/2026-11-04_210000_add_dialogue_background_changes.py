"""Диалог: фон сцены меняется по сегментам (background_changes), а не один на сцену

Revision ID: c5d6e7f8a9b0
Revises: 9b1c2d3e4f5a
Create Date: 2026-11-04 21:00:00.000000

Причина: фон сцены резолвился один раз на всю сцену — повествование «застывало»
на одном заднике, хотя диалог мог переходить между местами (салон автобуса →
ворота; домик → крыльцо → кромка леса). Теперь модель может задать 0–3 смены
фона внутри сцены через top-level ``background_changes`` (каждая — индекс первой
реплики нового места + свои модификаторы). Открывающий фон по-прежнему задаёт
``background_modifier_tags``.

Изменение JSON-схемы диалога (все активные варианты): в корень ответа добавляется
``background_changes``. Схема общая для всех вариантов, поэтому замена делается
строковой правкой идентичного JSON-блока. Каждая правка публикуется новой версией
(append-only), старые версии гасятся. Миграция идемпотентна: вариант с уже
заменённой схемой пропускается.
"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = '9b1c2d3e4f5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Точный JSON-блок схемы в активных шаблонах диалога (2 пробела отступа). Это
# текущее состояние после миграции 2026-11-04_200500 (top-level
# background_modifier_tags, без background_changes).
_SCHEMA_OLD = (
    "{\n"
    '  "background_modifier_tags": [string],\n'
    '  "dialogue_lines": [\n'
    '    { "kind": string, "character_name": string|null, "text": string }\n'
    "  ]\n"
    "}"
)

_SCHEMA_NEW = (
    "{\n"
    '  "background_modifier_tags": [string],\n'
    '  "background_changes": [\n'
    '    { "at_line": integer, "location_slug": string|null, "background_modifier_tags": [string] }\n'
    '  ],\n'
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
        # Удаляем только строки с новой схемой (top-level background_changes).
        bind.execute(
            sa.text(
                "DELETE FROM prompts WHERE key = 'dialogue' AND variant = :variant "
                "AND system_template LIKE :needle"
            ),
            {"variant": variant, "needle": '%"background_changes": [%'},
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
