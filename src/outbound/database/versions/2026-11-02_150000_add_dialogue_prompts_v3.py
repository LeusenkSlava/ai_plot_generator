"""Add prompt version 3 for dialogue (nsfw): concrete physical narration of intimate acts

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-02 15:00:00.000000

Причина: version 2 диалога давал только общий список того, что описывает
narration («movement, gestures, reactions, atmosphere, sensation»), плюс content
policy с «never gratuitous». Для откровенных сцен модель систематически уходила в
эвфемизм/метафору вместо конкретной физики: «губы смыкаются вокруг него», «она не
отрывается», а весь акт прятался за один символический жест («счёт пульса»). Читатель
не понимал, что именно происходит.

Version 3 (только вариант nsfw):
- добавляет инструкцию писать интимный акт конкретно и физически, бит за битом:
  называть части тела и что каждая делает, с сенсорными деталями (тепло, влажность,
  давление, вкус, фактура, ритм, глубина, движение, звук, дыхание);
- запрещает прятать акт за метафорой, эвфемизмом или одним символическим жестом;
- ориентирует эротику на мужскую аудиторию и мужской POV протагониста: фокус на теле
  женщины и её действиях, на его физическом удовольствии и возбуждении.
"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Тексты ниже повторяют version 2 (единственный источник правды — таблица prompts,
# поэтому миграция самодостаточна) и добавляют только новый блок «физики» — он есть
# исключительно в варианте nsfw и вставляется между блоком «For each line» и
# плейсхолдерами ассетов/протагониста.
_DIALOGUE_OPENING_NSFW = """You are a professional author of adult (18+) visual novels. Based on the description of the scene and the list of characters, write the scene that takes place in it."""

_DIALOGUE_PREAMBLE = """ Write lines only for the characters listed in the «Scene participants» block; the other characters of the novel do not appear or speak in this scene. Decide the number of lines yourself based on the content of the scene — usually 8 to 16, but no fewer than 6. Do not cut the scene off mid-sentence: bring the scene's key conversation to a logical point instead of cutting it on someone else's hook line. Do not end the scene with a concluding thought or a moral that spells out what was already shown: the scene's final line should leave a concrete detail, action, or line, not an interpretation; avoid turns of phrase like «кажется», «может», «наверное», «это и называется». Do not summarize the climax (a performance, a confession, a decisive act) as an outcome: show it beat by beat — at least one crisis moment within the event and its resolution, before it concludes. Open the scene so it continues from the previous one: if the story picks up in the same place and moment, continue from where it left off; if the time or place has changed, ground the reader with a short transition (where the protagonist is now, how they got here, or what brought them) before the conversation gets going. {choice_hint}"""

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

# Новое в version 3: конкретная физика интимного акта + ориентация на мужскую
# аудиторию. Только для nsfw.
_DIALOGUE_NSFW_PHYSICALITY = """\nWhen the scene contains an explicit intimate or sexual act, the narration must render it concretely and physically, beat by beat. Name the body parts and what each one does — lips, tongue, mouth, throat, hands, fingers, hips, cock — and ground every beat in sensory specifics: warmth, wetness, pressure, taste, texture, rhythm, depth, motion, sound, breath. Show how the act begins, builds and finishes step by step; do not fade it into metaphor, euphemism, an off-screen ellipsis, or a single symbolic gesture such as a pulse or a gaze. Write the erotic content for a male audience, from the male protagonist's point of view: keep the focus on the woman's body and what she does to him, and on his physical pleasure and arousal. Describe her mouth, her hands, her movements and her body concretely rather than replacing them with abstract feeling."""

_DIALOGUE_NSFW_CONTENT_POLICY = """Content policy: every character is an adult (18+); dialogue and narration may include explicit adult and erotic content between consenting adults, written in character and serving the scene's conflict and change — never gratuitous and never involving minors."""

_DIALOGUE_USER = """Novel characters:
{cast}{asset_catalog}{story_context_block}{current_outfits_block}{previous_scene_block}{previous_lines_block}{used_phrases_block}
Scene: {scene_title}
Scene description: {scene_description}
This scene takes place at: {place_time}.
Scene participants: {scene_participants}"""


def _dialogue_system() -> str:
    return (
        _DIALOGUE_OPENING_NSFW
        + _DIALOGUE_PREAMBLE
        + _FOR_EACH_LINE_BLOCK
        + _DIALOGUE_NSFW_PHYSICALITY
        + "{protagonist_block}{assets_block}"
        + "\n"
        + _DIALOGUE_NSFW_CONTENT_POLICY
        + "\n{russian_note}"
    )


# В version 3 меняется только dialogue (и только вариант nsfw).
_V3_KEYS = ("dialogue",)


def upgrade() -> None:
    """Upgrade schema: version 3 промпта dialogue (nsfw), деактивация version 2 (nsfw)."""
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
    for key in _V3_KEYS:
        rows.append(
            {
                'key': key,
                'variant': 'nsfw',
                'version': 3,
                'system_template': _dialogue_system(),
                'user_template': _DIALOGUE_USER,
                'is_active': True,
                'created_at': now,
                'updated_at': now,
            }
        )
    op.bulk_insert(prompts_table, rows)

    # Деактивируем version 2 для переизданного ключа (только вариант nsfw).
    op.execute(
        sa.text(
            "UPDATE prompts SET is_active=false "
            "WHERE key IN ('dialogue') AND variant = 'nsfw' AND version = 2"
        )
    )


def downgrade() -> None:
    """Downgrade schema: вернуть активность version 2 (nsfw) и убрать version 3."""
    op.execute(sa.text("DELETE FROM prompts WHERE version = 3 AND variant = 'nsfw'"))
    op.execute(
        sa.text(
            "UPDATE prompts SET is_active=true "
            "WHERE key IN ('dialogue') AND variant = 'nsfw' AND version = 2"
        )
    )
