"""Add NSFW heat levels: nsfw_low, nsfw_medium, nsfw_high

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-02 16:00:00.000000

Причина: вариант ``nsfw`` был единственным и сразу максимально откровенным.
Нужна градация по нарастанию «жара»:

- ``nsfw_low`` — взрослая романтика с напряжением и намёками, интимные сцены
  уходят в затемнение до откровенности;
- ``nsfw_medium`` — эротическая романтика: нагота, ласки, близость описываются
  чувственно, но без грубой анатомии и пошаговой механики;
- ``nsfw_high`` — прежний уровень ``nsfw``: конкретная физика интимного акта
  (копия активных текстов варианта ``nsfw``).

``nsfw`` остаётся в таблице и в enum как устаревший алиас высокого уровня для
обратной совместимости API: существующие новеллы и клиенты продолжают работать.

Тексты low/medium строятся из активных текстов варианта ``default`` (чтобы не
дублировать общую структуру и JSON-схемы) плюс адресный блок «Heat level» для
каждого ключа. Это единственное отличие: базовая структура, плейсхолдеры и
схемы совпадают с default.
"""
from datetime import UTC, datetime
from typing import Callable, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Все ключи промптов: у каждого варианта должен быть полный комплект.
_KEYS = (
    "novel",
    "character",
    "roadmap",
    "scene",
    "dialogue",
    "story_context",
    "branch_roadmap",
    "scene_validator",
)

# Общий блок уровня. Вставляется после {russian_note}, поэтому не содержит
# плейсхолдеров и не ломает рендер шаблона.
_LOW_COMMON = (
    "Heat level — low (adult romance). Every character is an adult (18+). "
    "Attraction, romantic tension, kisses, embraces and light touching are welcome, "
    "but intimacy must stay suggestive and fade to black before anything explicit: "
    "no nudity below the waist, no sexual acts, no anatomical detail and no crude vocabulary."
)

_MEDIUM_COMMON = (
    "Heat level — medium (adult erotic romance). Every character is an adult (18+). "
    "You may show nudity, undressing, foreplay, kissing and touching the body, oral and "
    "manual caresses, arousal and sex between consenting adults. Keep it sensual and "
    "restrained rather than pornographic: favour breath, warmth, sensation, emotion and "
    "the characters' reactions over crude anatomical vocabulary, and do not spell out "
    "graphic step-by-step mechanics."
)

_LOW_NOTES: dict[str, str] = {
    "novel": (
        "Build the story as a slow-burn adult romance: the heat grows through glances, "
        "tension, closeness and choice, and the plot never turns into a sequence of erotic scenes."
    ),
    "character": (
        "voice_notes may convey charm, flirtation and a sensual manner of speech, "
        "but no explicit sexual detail."
    ),
    "roadmap": (
        "Romantic beats may appear, but they must carry their own event, conflict and change "
        "and must not become the step's sole purpose."
    ),
    "scene": (
        "The scene may establish romantic tension, a charged atmosphere, a kiss or physical "
        "closeness, but its description must not contain explicit acts or nudity."
    ),
    "dialogue": (
        "When the scene turns intimate, render it through tension, breath, glances, touch and "
        "what is left unsaid, then cut away; do not describe the act itself."
    ),
    "story_context": (
        "Record romantic developments (a kiss, a confession, growing closeness) as ordinary "
        "plot facts without censorship, but omit explicit sexual detail."
    ),
    "branch_roadmap": (
        "The branch may include romantic beats, but they need their own conflict and change "
        "and must not replace the plot."
    ),
    "scene_validator": (
        "An adult romantic tone is not a defect: judge only the three axes and do not penalise "
        "the scene for being sensual or for fading to black."
    ),
}

_MEDIUM_NOTES: dict[str, str] = {
    "novel": (
        "Build the story as an adult erotic romance: desire and intimacy are part of the plot "
        "and may be shown in sensual, non-graphic detail, but the story must not turn into a "
        "sequence of sex scenes."
    ),
    "character": (
        "voice_notes may convey seduction, sensuality and an openly erotic manner of speech, "
        "in character and without crude vocabulary."
    ),
    "roadmap": (
        "Steps may include erotic beats (a seduction, a night together) between consenting "
        "adults; each still needs its own event, conflict and change, and intimacy must not "
        "become the step's sole purpose."
    ),
    "scene": (
        "The scene may establish an erotic situation — undressing, foreplay, a night together — "
        "between consenting adults; describe it concretely enough to set up the dialogue, but "
        "keep it sensual rather than graphic."
    ),
    "dialogue": (
        "When the scene contains an intimate situation, describe nudity, foreplay, hands and "
        "mouths on the body, arousal and sex between consenting adults, focusing on sensation, "
        "breath, warmth and the characters' reactions; keep the vocabulary tasteful and do not "
        "spell out graphic step-by-step mechanics."
    ),
    "story_context": (
        "Record intimate developments (nudity, a night together, a new level of closeness) as "
        "ordinary plot facts without censorship or judgment, but keep the wording brief and "
        "non-graphic."
    ),
    "branch_roadmap": (
        "The branch may include erotic beats between consenting adults, but they need their own "
        "conflict and change and must not replace the plot."
    ),
    "scene_validator": (
        "Adult erotic content is not a defect: judge only the three axes and do not penalise the "
        "scene for depicting sensuality or sex between adults."
    ),
}


def _low_suffix(key: str) -> str:
    return "\n" + _LOW_COMMON + " " + _LOW_NOTES[key]


def _medium_suffix(key: str) -> str:
    return "\n" + _MEDIUM_COMMON + " " + _MEDIUM_NOTES[key]


def _insert_variant(
    *,
    source_variant: str,
    target_variant: str,
    suffix_for_key: Callable[[str], str],
) -> None:
    """Копирует активные тексты ``source_variant`` в новый вариант ``target_variant``.

    Копируется по одной строке на каждый ключ: версия всегда 1 (вариант новый),
    ``is_active = true``. ``system_template`` дополняется суффиксом уровня.
    """
    bind = op.get_bind()
    now = datetime.now(UTC)

    for key in _KEYS:
        bind.execute(
            sa.text(
                """
                INSERT INTO prompts
                    (key, variant, version, system_template, user_template, is_active, created_at, updated_at)
                SELECT key, :target_variant, 1, system_template || :suffix, user_template, true, :now, :now
                FROM prompts
                WHERE key = :key AND variant = :source_variant AND is_active
                """
            ),
            {
                "key": key,
                "source_variant": source_variant,
                "target_variant": target_variant,
                "suffix": suffix_for_key(key),
                "now": now,
            },
        )

    # Защита от тихой генерации неполного комплекта: активная версия должна быть
    # ровно у каждого ключа, иначе генератор упадёт с PromptNotFoundError.
    seeded = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM prompts "
            "WHERE variant = :variant AND version = 1 AND is_active"
        ),
        {"variant": target_variant},
    ).scalar_one()
    if seeded != len(_KEYS):
        raise RuntimeError(
            f"Prompt variant {target_variant!r}: expected {len(_KEYS)} active rows, got {seeded}"
        )


def upgrade() -> None:
    """Upgrade schema: сид вариантов nsfw_low, nsfw_medium и nsfw_high."""
    # high — точная копия текущего максимального варианта nsfw.
    _insert_variant(
        source_variant="nsfw",
        target_variant="nsfw_high",
        suffix_for_key=lambda _key: "",
    )
    # low/medium — база default + адресный блок уровня.
    _insert_variant(
        source_variant="default",
        target_variant="nsfw_low",
        suffix_for_key=_low_suffix,
    )
    _insert_variant(
        source_variant="default",
        target_variant="nsfw_medium",
        suffix_for_key=_medium_suffix,
    )


def downgrade() -> None:
    """Downgrade schema: убрать варианты градации, оставив прежний nsfw."""
    op.execute(
        sa.text(
            "DELETE FROM prompts "
            "WHERE variant IN ('nsfw_low', 'nsfw_medium', 'nsfw_high')"
        )
    )
