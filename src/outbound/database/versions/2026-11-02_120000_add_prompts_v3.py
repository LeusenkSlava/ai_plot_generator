"""Add prompt version 3 for scene (scene description carries concrete per-scene beat/action)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-02 12:00:00.000000

Причина: version 2 сцены намеренно вырезал действие из описания
(«Do NOT describe the action or sensations here — that is done later as narration
lines in the dialogue»), но диалог в итоге получал только это пустое описание, а
событие шага из roadmap.event никуда дальше не попадало — смысл терялся.

Version 3:
- возвращает действие в описание сцены (убирает «без действия/ощущений»);
- заставляет описывать только долю ТЕКУЩЕЙ сцены (scene N of M), а не весь шаг сразу,
  поэтому событие разделяется между сценами заранее и диалог каждой сцены не
  повторяет чужие биты;
- диалог по-прежнему строится из scene.description — теперь уже с конкретным действием.
"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCENE_OPENING_DEFAULT = """You are a screenwriter for interactive visual novels. Based on the description of the story and the current roadmap step, create the next scene of this step. It should continue the previous scenes without repeating them and move the plot toward the step's event — carry its conflict and reach its change. The scene should unfold the step's event and establish the place and situation of the action, but not retell the dialogues themselves. Put the step's conflict into the description as a concrete crisis or obstacle (what makes the event hard), not just its outcome. Specify:"""
_SCENE_OPENING_NSFW = """You are a professional author of adult (18+) visual novels. Based on the description of the story and the current roadmap step, create the next scene of this step. It should continue the previous scenes without repeating them and move the plot toward the step's event — carry its conflict and reach its change. The scene should unfold the step's event and establish the place and situation of the action, but not retell the dialogues themselves. Put the step's conflict into the description as a concrete crisis or obstacle (what makes the event hard), not just its outcome. Specify:"""

# Ключевое отличие от v2: описание — конкретный бит ТЕКУЩЕЙ сцены с действием,
# а не пустая завязка. «Scene number within the step» уже есть в user-шаблоне и
# задаёт позицию (N of M) для разреза события по сценам.
_SCENE_DESCRIPTION_V3 = "2. description - a concrete description of THIS scene's beat: the place, the situation, the conflict, and what actually happens and develops in this scene — the action and its stakes, not just the atmosphere. 2-4 sentences, no more than 400 characters. Cover only this scene's slice of the step's event (see the scene number within the step below): do not compress the whole step into this scene, do not repeat another scene's beat, and do not write the dialogue lines themselves — they are generated later from this description."

_SCENE_ITEMS = """1. title - a short title for the scene.
{description_item}
3. characters - the names of the characters who are in this scene by place and time (exactly as in the character list). Include only those who belong here; do not include a character who does not belong here (for example, someone who never leaves their own location — in a scene elsewhere). Including the protagonist is optional: they are always present and are added automatically.
4. location_slug - the slug of the scene's location: the same as the roadmap step's (empty string if the step does not set one).
5. time_of_day - the slug of the scene's time of day (empty string if the step does not set one); it may change within the step if it is the same day.
6. day - the story day number (integer from 1): the same as the roadmap step's.
If the scene starts later in time or in a different place than the previous one, note this gap directly in description.
Answer STRICTLY as JSON matching this schema:
{
  "title": string,
  "description": string,
  "characters": [string],
  "location_slug": string,
  "time_of_day": string,
  "day": integer
}"""

_SCENE_NSFW_CONTENT_POLICY = "Content policy: every character is an adult (18+); the scene may establish an intimate or erotic situation between consenting adults as a concrete crisis or mood rather than gratuitous description."

_SCENE_USER = """Story title: {title}
Narrative tone: {tone}{characters_block}
Step place and time: {step_place_time}.
Roadmap step: {step_title}
Step event: {step_event}
Step conflict: {step_conflict}
Step change: {step_change}
Scene number within the step: {step_position} of {scenes_count}{story_context_block}{previous_scenes_block}"""


def _scene_system(variant: str) -> str:
    opening = _SCENE_OPENING_NSFW if variant == "nsfw" else _SCENE_OPENING_DEFAULT
    policy = (
        "\n" + _SCENE_NSFW_CONTENT_POLICY if variant == "nsfw" else ""
    )
    # .replace(), а не .format(): в тексте JSON-схемы есть литеральные фигурные скобки.
    items = _SCENE_ITEMS.replace("{description_item}", _SCENE_DESCRIPTION_V3)
    return opening + "\n" + items + policy + "\n{russian_note}"


# В version 3 меняется только scene.
_V3_KEYS = ("scene",)


def upgrade() -> None:
    """Upgrade schema: version 3 промпта scene, деактивация version 2."""
    prompts_table = sa.table(
        'prompts',
        sa.column('key', sa.String()),
        sa.column('variant', sa.String()),
        sa.column('version', sa.Integer()),
        sa.column('system_template', sa.Text()),
        sa.column('user_template', sa.Text()),
        sa.column('is_active', sa.Boolean()),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)

    rows = []
    for variant in ("default", "nsfw"):
        for key in _V3_KEYS:
            rows.append(
                {
                    'key': key,
                    'variant': variant,
                    'version': 3,
                    'system_template': _scene_system(variant),
                    'user_template': _SCENE_USER,
                    'is_active': True,
                    'created_at': now,
                    'updated_at': now,
                }
            )
    op.bulk_insert(prompts_table, rows)

    # Деактивируем version 2 для переизданного ключа (по обоим вариантам).
    op.execute(
        sa.text(
            "UPDATE prompts SET is_active=false "
            "WHERE key IN ('scene') AND version = 2"
        )
    )


def downgrade() -> None:
    """Downgrade schema: вернуть активность version 2 и убрать version 3."""
    op.execute(sa.text("DELETE FROM prompts WHERE version = 3"))
    op.execute(
        sa.text(
            "UPDATE prompts SET is_active=true "
            "WHERE key IN ('scene') AND version = 2"
        )
    )
