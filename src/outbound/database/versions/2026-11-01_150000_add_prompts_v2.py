"""Промпты dialogue и scene version 2: тип реплики kind с narration

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-01 15:00:00.000000

"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Общий блок «For each line» (kind + character_name, допускающий null) используется
# и в default, и в nsfw; между вариантами отличаются только роль автора и Content policy.
_FOR_EACH_LINE_BLOCK = """For each line, specify:
1. kind - one of "speech", "thought", "narration".
   - "speech": a character speaks out loud; set character_name to the speaker's name.
   - "thought": the protagonist's inner monologue (not spoken aloud); set character_name to the protagonist's name.
   - "narration": the narrator's description of what happens physically and emotionally — movement, gestures, reactions, atmosphere, sensation. Narration has no speaker: set character_name to null. It renders as prose and has no sprite.
2. character_name - the name of the speaking character for speech/thought, exactly as in the list; null for narration.
3. text - the text of the line (for narration, the descriptive prose).
Interleave narration beats with speech and thoughts so the scene reads as flowing prose, not a bare transcript. Every narration beat must show something the dialogue itself does not state — never paraphrase the surrounding lines. Keep enough speech/thought to carry the characters' voices; do not replace the conversation with narration. The final line of a scene that ends in a choice must be speech or thought, not narration.
Answer STRICTLY as JSON matching this schema:
{
  "dialogue_lines": [
    { "kind": string, "character_name": string|null, "text": string }
  ]
}"""

_DIALOGUE_OPENING_DEFAULT = """You are a screenwriter for interactive visual novels. Based on the description of the scene and the list of characters, write the dialogue that takes place in it."""
_DIALOGUE_OPENING_NSFW = """You are a professional author of adult (18+) visual novels. Based on the description of the scene and the list of characters, write the scene that takes place in it."""

_DIALOGUE_PREAMBLE = """ Write lines only for the characters listed in the «Scene participants» block; the other characters of the novel do not appear or speak in this scene. Decide the number of lines yourself based on the content of the scene — usually 8 to 16, but no fewer than 6. Do not cut the scene off mid-sentence: bring the scene's key conversation to a logical point instead of cutting it on someone else's hook line. Do not end the scene with a concluding thought or a moral that spells out what was already shown: the scene's final line should leave a concrete detail, action, or line, not an interpretation; avoid turns of phrase like «кажется», «может», «наверное», «это и называется». Do not summarize the climax (a performance, a confession, a decisive act) as an outcome: show it beat by beat — at least one crisis moment within the event and its resolution, before it concludes. Open the scene so it continues from the previous one: if the story picks up in the same place and moment, continue from where it left off; if the time or place has changed, ground the reader with a short transition (where the protagonist is now, how they got here, or what brought them) before the conversation gets going. {choice_hint}"""

_DIALOGUE_NSFW_CONTENT_POLICY = """Content policy: every character is an adult (18+); dialogue and narration may include explicit adult and erotic content between consenting adults, written in character and serving the scene's conflict and change — never gratuitous and never involving minors."""

# Пункт 2 scene в v2: описание — только завязка (место, время, ситуация, конфликт),
# действие и ощущения выносятся в narration.
_SCENE_DESCRIPTION_V2 = "2. description - a short setup of place, time, situation and conflict (2-4 sentences, no more than 400 characters). Do NOT describe the action or sensations here — that is done later as narration lines in the dialogue."

_SCENE_OPENING_DEFAULT = """You are a screenwriter for interactive visual novels. Based on the description of the story and the current roadmap step, create the next scene of this step. It should continue the previous scenes without repeating them and move the plot toward the step's event — carry its conflict and reach its change. The scene should unfold the step's event and establish the place and situation of the action, but not retell the dialogues themselves. Put the step's conflict into the description as a concrete crisis or obstacle (what makes the event hard), not just its outcome. Specify:"""
_SCENE_OPENING_NSFW = """You are a professional author of adult (18+) visual novels. Based on the description of the story and the current roadmap step, create the next scene of this step. It should continue the previous scenes without repeating them and move the plot toward the step's event — carry its conflict and reach its change. The scene should unfold the step's event and establish the place and situation of the action, but not retell the dialogues themselves. Put the step's conflict into the description as a concrete crisis or obstacle (what makes the event hard), not just its outcome. Specify:"""

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

_DIALOGUE_USER = """Novel characters:
{cast}{asset_catalog}{story_context_block}{current_outfits_block}{previous_scene_block}{previous_lines_block}{used_phrases_block}
Scene: {scene_title}
Scene description: {scene_description}
This scene takes place at: {place_time}.
Scene participants: {scene_participants}"""

_SCENE_USER = """Story title: {title}
Narrative tone: {tone}{characters_block}
Step place and time: {step_place_time}.
Roadmap step: {step_title}
Step event: {step_event}
Step conflict: {step_conflict}
Step change: {step_change}
Scene number within the step: {step_position} of {scenes_count}{story_context_block}{previous_scenes_block}"""


def _dialogue_system(variant: str) -> str:
    opening = _DIALOGUE_OPENING_NSFW if variant == "nsfw" else _DIALOGUE_OPENING_DEFAULT
    policy = (
        "\n" + _DIALOGUE_NSFW_CONTENT_POLICY if variant == "nsfw" else ""
    )
    return (
        opening
        + _DIALOGUE_PREAMBLE
        + _FOR_EACH_LINE_BLOCK
        + "{protagonist_block}{assets_block}"
        + policy
        + "\n{russian_note}"
    )


def _scene_system(variant: str) -> str:
    opening = _SCENE_OPENING_NSFW if variant == "nsfw" else _SCENE_OPENING_DEFAULT
    policy = (
        "\n" + _SCENE_NSFW_CONTENT_POLICY if variant == "nsfw" else ""
    )
    # Подстановка через .replace(), а не .format(): в JSON-схеме есть литеральные
    # фигурные скобки, которые .format() принял бы за плейсхолдеры.
    items = _SCENE_ITEMS.replace("{description_item}", _SCENE_DESCRIPTION_V2)
    return opening + "\n" + items + policy + "\n{russian_note}"


# Ключи, переизданные в version 2. story_context остаётся в version 1: его шаблон
# не менялся, изменилась только сборка диалога в коде.
_V2_KEYS = ("dialogue", "scene")


def upgrade() -> None:
    """Upgrade schema: version 2 промптов dialogue/scene, деактивация version 1."""
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
        for key in _V2_KEYS:
            system = _dialogue_system(variant) if key == "dialogue" else _scene_system(variant)
            user = _DIALOGUE_USER if key == "dialogue" else _SCENE_USER
            rows.append(
                {
                    'key': key,
                    'variant': variant,
                    'version': 2,
                    'system_template': system,
                    'user_template': user,
                    'is_active': True,
                    'created_at': now,
                    'updated_at': now,
                }
            )
    op.bulk_insert(prompts_table, rows)

    # Деактивация version 1 переизданных ключей в обоих вариантах (default, nsfw).
    op.execute(
        sa.text(
            "UPDATE prompts SET is_active=false "
            "WHERE key IN ('dialogue', 'scene') AND version = 1"
        )
    )


def downgrade() -> None:
    """Downgrade schema: вернуть активность version 1 и убрать version 2."""
    op.execute(sa.text("DELETE FROM prompts WHERE version = 2"))
    op.execute(
        sa.text(
            "UPDATE prompts SET is_active=true "
            "WHERE key IN ('dialogue', 'scene') AND version = 1"
        )
    )
