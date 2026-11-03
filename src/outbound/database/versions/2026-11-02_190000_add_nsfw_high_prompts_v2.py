"""Промпты scene и dialogue version 2 для nsfw_high: интимный акт выводится в текст сцены

Revision ID: b8c9d0e1f2a3
Revises: f6a7b8c9d0e1
Create Date: 2026-11-02 19:00:00.000000

Предпосылка: на варианте ``nsfw_high`` интимная линия смещалась в фон сюжета.
Промпт dialogue требовал физики акта только когда сцена явно интимна, но описание
сцены акта не содержало: промпт scene (унаследованный от общего ``nsfw``) предписывал
давать интимность через конфликт или настроение, ограничивал описание 2–4
предложениями и требовал отдельный бит у каждой сцены. В результате шаг делился на
подход и поцелуй, акт оставался за кадром, а диалог следовал описанию.

Изменения в version 2 (только вариант ``nsfw_high``):

- ``scene``: если событие или change шага интимные, описание обязано нести сам акт
  конкретно (кто, с кем, какими частями тела, до какого предела доходит сцена);
  описание не обрывается на поцелуе, признании или согласии; при разделении шага на
  несколько сцен акт раскладывается по ним (завязка → акт → развязка); content
  policy переписана: описание — бриф для диалога, затемнение и метафора вместо
  акта запрещены;
- ``dialogue``: физика акта требуется на любой интимной сцене — по описанию или по
  event/change шага; описание задаёт стартовую точку, но не предел сцены; сцена не
  может закончиться на поцелуе, раздевании или согласии; фоновые персонажи (другие
  пары) допускаются в narration без реплик и мыслей;
- ``dialogue`` user-шаблон получает ``{step_block}``: шаг роадмапа (title/event/
  conflict/change) и позицию сцены в шаге (N из M). До этого диалог видел только
  описание сцены. Значение собирает ``DialoguePromptBuilder``, позицию сцены отдаёт
  ``DialogueContextLoader``.

Остальные варианты (``default``, ``nsfw_low``, ``nsfw_medium``, устаревший
``nsfw``) не изменяются: правка относится только к верхнему уровню.
"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCENE_SYSTEM = """You are a professional author of adult (18+) visual novels. Based on the description of the story and the current roadmap step, create the next scene of this step. It should continue the previous scenes without repeating them and move the plot toward the step's event — carry its conflict and reach its change. The scene should unfold the step's event and establish the place and situation of the action, but not retell the dialogues themselves. Put the step's conflict into the description as a concrete crisis or obstacle (what makes the event hard), not just its outcome. Specify:
1. title - a short title for the scene.
2. description - a concrete description of THIS scene's beat: the place, the situation, the conflict, and what actually happens and develops in this scene — the action and its stakes, not just the atmosphere. 3-5 sentences, no more than 600 characters. Cover only this scene's slice of the step's event (see the scene number within the step below): do not compress the whole step into this scene, do not repeat another scene's beat, and do not write the dialogue lines themselves — they are generated later from this description.
   If the step's event or change is intimate or sexual, the description MUST carry the sexual content of this scene itself, concretely: who does what to whom, with which body parts, and how far this scene goes (undressing, caresses, oral sex, penetration, climax). Never end the description at a kiss, a confession of desire or consent when the act belongs to this scene — name the act. When the step is split into several scenes, split the act: the first scene covers the onset (undressing, foreplay, first contact), the last scene the act itself, the climax and the aftermath; every scene must advance the intimacy rather than stop before it. If the scene shows several couples at once (an orgy), name at least two of the pairs and what they are doing to each other concretely — mouths, hands, bodies, penetration — not merely that they embraced or caressed: a group scene that is only mentioned is not shown.
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
}
Content policy: every character is an adult (18+). The scene description is the brief from which the dialogue is written: when the step is intimate, the description must state the sexual content plainly and concretely — the act, the bodies involved and how far it goes. Do not fade to black, do not replace the act with a metaphor, and do not soften it into mere mood; explicit detail is required here because it serves the step's event and change.
{russian_note}"""

_SCENE_USER = """Story title: {title}
Narrative tone: {tone}{characters_block}
Step place and time: {step_place_time}.
Roadmap step: {step_title}
Step event: {step_event}
Step conflict: {step_conflict}
Step change: {step_change}
Scene number within the step: {step_position} of {scenes_count}{story_context_block}{previous_scenes_block}"""

_DIALOGUE_SYSTEM = """You are a professional author of adult (18+) visual novels. Based on the description of the scene and the list of characters, write the scene that takes place in it. Write speech and thoughts only for the characters listed in the «Scene participants» block: the other characters of the novel do not speak and get no lines. They may still appear in narration as background when the scene description places them there (a crowd, other couples on the beach), but the narration must not give them dialogue or inner thoughts. Decide the number of lines yourself based on the content of the scene — usually 8 to 16, but no fewer than 6. Do not cut the scene off mid-sentence: bring the scene's key conversation to a logical point instead of cutting it on someone else's hook line. Do not end the scene with a concluding thought or a moral that spells out what was already shown: the scene's final line should leave a concrete detail, action, or line, not an interpretation; avoid turns of phrase like «кажется», «может», «наверное», «это и называется». Do not summarize the climax (a performance, a confession, a decisive act) as an outcome: show it beat by beat — at least one crisis moment within the event and its resolution, before it concludes. Open the scene so it continues from the previous one: if the story picks up in the same place and moment, continue from where it left off; if the time or place has changed, ground the reader with a short transition (where the protagonist is now, how they got here, or what brought them) before the conversation gets going. {choice_hint}For each line, specify:
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
}
When the scene is intimate or sexual — its description contains an intimate or sexual act, or the roadmap step's event or change is the act itself — the narration must render the act concretely and physically, beat by beat, and must not skip it or cut away from it. Name the body parts and what each one does — lips, tongue, mouth, throat, hands, fingers, hips, cock — and ground every beat in sensory specifics: warmth, wetness, pressure, taste, texture, rhythm, depth, motion, sound, breath. Show how the act begins, builds and finishes step by step; do not fade it into metaphor, euphemism, an off-screen ellipsis, or a single symbolic gesture such as a pulse or a gaze, and do not let the scene end at a kiss, undressing or consent while the act itself is still ahead. If the scene description stops at the threshold of the act, continue from it into the act — the description is a starting point, not a limit; if this is the last scene of the step, the act must happen here rather than be postponed. Write the erotic content for a male audience, from the male protagonist's point of view: keep the focus on the woman's body and what she does to him, and on his physical pleasure and arousal. Describe her mouth, her hands, her movements and her body concretely rather than replacing them with abstract feeling. When other couples are visible around them, show their acts in the background just as concretely — briefly, but with bodies and motion — so the reader sees the orgy around the protagonist, not just a mention of it.{protagonist_block}{assets_block}
Content policy: every character is an adult (18+); dialogue and narration may include explicit adult and erotic content between consenting adults, written in character and serving the scene's conflict and change. When the scene is intimate, be explicit and concrete; never involve minors.
{russian_note}"""

_DIALOGUE_USER = """Novel characters:
{cast}{asset_catalog}{story_context_block}{current_outfits_block}{previous_scene_block}{previous_lines_block}{used_phrases_block}

{step_block}
Scene: {scene_title}
Scene description: {scene_description}
This scene takes place at: {place_time}.
Scene participants: {scene_participants}"""


def _insert_version2(bind: sa.Connection, key: str, system: str, user: str) -> None:
    """Публикует version 2 ключа в nsfw_high; активные версии ключа деактивируются."""
    now = datetime.now(UTC)
    bind.execute(
        sa.text(
            "UPDATE prompts SET is_active = false, updated_at = :now "
            "WHERE key = :key AND variant = 'nsfw_high' AND is_active"
        ),
        {"key": key, "now": now},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO prompts
                (key, variant, version, system_template, user_template, is_active, created_at, updated_at)
            VALUES (:key, 'nsfw_high', 2, :system, :user, true, :now, :now)
            """
        ),
        {"key": key, "system": system, "user": user, "now": now},
    )


def upgrade() -> None:
    """Upgrade schema: version 2 промптов scene и dialogue для nsfw_high."""
    bind = op.get_bind()
    _insert_version2(bind, "scene", _SCENE_SYSTEM, _SCENE_USER)
    _insert_version2(bind, "dialogue", _DIALOGUE_SYSTEM, _DIALOGUE_USER)

    # Проверка полноты: обе version 2 (scene и dialogue) должны стать активными,
    # иначе один из промптов останется старой версией.
    active = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM prompts "
            "WHERE variant = 'nsfw_high' AND version = 2 AND is_active "
            "AND key IN ('scene', 'dialogue')"
        )
    ).scalar_one()
    if active != 2:
        raise RuntimeError(
            f"nsfw_high prompts v2: expected 2 active rows, got {active}"
        )


def downgrade() -> None:
    """Downgrade schema: вернуть version 1 и удалить version 2."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM prompts "
            "WHERE variant = 'nsfw_high' AND version = 2 AND key IN ('scene', 'dialogue')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE prompts SET is_active = true "
            "WHERE variant = 'nsfw_high' AND version = 1 AND key IN ('scene', 'dialogue')"
        )
    )
