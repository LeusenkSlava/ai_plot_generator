"""Add prompts table (versioned prompt templates) and novels.prompt_variant

Revision ID: e7b4a2d9c0f5
Revises: f4a6c8d0e2b5
Create Date: 2026-11-01 12:00:00.000000

"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b4a2d9c0f5'
down_revision: Union[str, Sequence[str], None] = 'f4a6c8d0e2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Тексты варианта ``default`` лежат здесь (в миграции), а не в коде: единственный
# источник правды для промптов — таблица ``prompts``. В рантайме эти тексты не
# читаются; отсутствие активной версии в БД — ошибка (``PromptNotFoundError``).
_DEFAULT_PROMPTS: dict[str, tuple[str, str]] = {
    "novel": (
        """You are a screenwriter for interactive visual novels. Based on the user's tags and description, create the creative foundation of the story for further generation. {json_instruction}{codex_block}
{russian_note}""",
        "{user_prompt}",
    ),
    "character": (
        """You are a screenwriter for interactive visual novels. Based on the description of the story and its tone, create a set of characters for the plot. Decide the number of characters yourself based on the scale of the story — usually 2 to 6. Be sure to include a protagonist (hero/heroine) and at least one antagonist or a significant supporting character. For each character, specify:
1. name - the character's name.
2. role - the role in the story (protagonist, antagonist, ally, love interest, etc.).
3. arc - a short description of the character's story arc.
4. voice_notes - notes on the character's manner of speech and personality that will help generate dialogues later.
5. is_protagonist - boolean. true ONLY for the protagonist, through whose eyes the player experiences the story; they have no sprite shown, and their inner thoughts are available in dialogues. There must be EXACTLY one protagonist.
Answer STRICTLY as JSON matching this schema:
{
  "characters": [
    {
      "name": string,
      "role": string,
      "arc": string,
      "voice_notes": string,
      "is_protagonist": boolean
    }
  ]
}{codex_block}
{russian_note}""",
        """Title: {title}
Description: {description}
Narrative tone: {tone}{codex_catalog}""",
    ),
    "roadmap": (
        """You are a screenwriter for interactive visual novels. Based on the description of the story and its tone, create a plot roadmap — {story_shape} Decide the number of steps yourself based on the scale of the story — usually 8 to 12; the more steps, the richer the story, but each step must move the plot forward rather than repeat the previous one. For each step, specify:
1. title - a short title for the step.
2. event - ONE completed event/beat that happens in this step; do not stretch the step over a whole arc — it should fit into 1–2 scenes.
3. conflict - what makes this event hard for the protagonist: an obstacle, a contradiction, a risk, or what is at stake; the scene must be able to dramatize it.
4. change - what changes for the protagonist by the end of the step: a decision, a feeling, or a shift in a relationship; one concrete consequence.
5. scenes_count - 1 or 2 for a regular step; the final step and steps with a character's resolution may have 2 or 3. Use 2/3 only if each scene has its own beat, otherwise the scene will replay the previous one.
6. location_slug - the slug of the location where the step takes place, ONLY from the location list (empty string if there is no list).
7. time_of_day - the slug of the step's time of day, ONLY from the time-of-day list (empty string if there is no list).
8. day - the story day number: an integer from 1, non-decreasing between steps; if the step takes place on the same day as the previous one, use the same number.
The story structure is Harmon's story circle of 8 beats. Keep this order; do not rearrange or skip beats:
1. Ordinary world — the protagonist in their ordinary life; convey their dissatisfaction or desire so that there is a reason to change.
2. Need — the protagonist's concrete goal/desire that sets the direction of the whole story; it is also the through-line from the story description (a mystery, a goal, coming home, an internal conflict) that you must not drop before the finale.
3. Go — an event knocks the protagonist out of ordinary life into an unfamiliar situation (the inciting event).
4. Search — the protagonist tries to reach the goal, hits obstacles, forms relationships. Around the middle — a turn that changes the stakes.
5. Find — the protagonist gets what they wanted, but in an unexpected or imperfect form.
6. Take — the find must be paid for: a loss, a conflict, a consequence. This is a real obstacle/threat of failure before the climax — do not lead straight to it.
7. Return — the protagonist returns to the familiar situation, but changed; the key event (a confession, a decision, a performance) plays out here.
8. Change — the final state of the protagonist/world and the story's takeaway; a resolution, not a cliffhanger cut on the eve.
Spread the beats across steps: 8 beats → 8–12 steps. The first and last beats usually take one step each; beats 4–6 can stretch over 2 steps. For significant characters (ally, rival, love interest) carry a mini-arc within these beats and resolve it by beats 7–8, not by appearing in a single scene.
Track when each significant character first enters the story. The first time a significant character appears, dedicate a step to establishing the meeting: where and how the protagonist meets them and what makes them start interacting. Do not write a step whose event already assumes an established relationship (someone already teaching, helping, or being close to the protagonist) unless an earlier step introduced them and set up that interaction. Treat the story premise (a lesson, friendship, romance) as a goal to build toward across the arc, not as the starting state of its first related scene.
Spread the action across place and time: adjacent steps may stay in the same location when the story flows naturally there; change location when the plot requires it (a move, a new activity, a new beat), not for the sake of variety. Every scene within a step must match the step's place and day.
Build event/conflict/change only on the characters from the list below; do not mention in event, conflict, or change characters who are not in the list (even if they exist in the universe) — scenes with such characters will not pass validation and will be regenerated.
{choice_instructions}Answer STRICTLY as JSON matching this schema:
{schema}
{russian_note}""",
        """Title: {title}
Description: {description}
Narrative tone: {tone}{place_time_catalog}{characters_block}""",
    ),
    "scene": (
        """You are a screenwriter for interactive visual novels. Based on the description of the story and the current roadmap step, create the next scene of this step. It should continue the previous scenes without repeating them and move the plot toward the step's event — carry its conflict and reach its change. The scene should unfold the step's event and establish the place and situation of the action, but not retell the dialogues themselves. Put the step's conflict into the description as a concrete crisis or obstacle (what makes the event hard), not just its outcome. Specify:
1. title - a short title for the scene.
2. description - a description of the place, time, situation, and conflict of the scene, from which the characters' dialogues will then be generated: 2-4 sentences, no more than 400 characters, no atmospheric details.
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
{russian_note}""",
        """Story title: {title}
Narrative tone: {tone}{characters_block}
Step place and time: {step_place_time}.
Roadmap step: {step_title}
Step event: {step_event}
Step conflict: {step_conflict}
Step change: {step_change}
Scene number within the step: {step_position} of {scenes_count}{story_context_block}{previous_scenes_block}""",
    ),
    "dialogue": (
        """You are a screenwriter for interactive visual novels. Based on the description of the scene and the list of characters, write the dialogue that takes place in it. Write lines only for the characters listed in the «Scene participants» block; the other characters of the novel do not appear or speak in this scene. Decide the number of lines yourself based on the content of the scene — usually 8 to 16, but no fewer than 6. Do not cut the scene off mid-sentence: bring the scene's key conversation to a logical point instead of cutting it on someone else's hook line. Do not end the scene with a concluding thought or a moral that spells out what was already shown: the scene's final line should leave a concrete detail, action, or line, not an interpretation; avoid turns of phrase like «кажется», «может», «наверное», «это и называется». Do not summarize the climax (a performance, a confession, a decisive act) as an outcome: show it beat by beat — at least one crisis moment within the event and its resolution, before it concludes. Open the scene so it continues from the previous one: if the story picks up in the same place and moment, continue from where it left off; if the time or place has changed, ground the reader with a short transition (where the protagonist is now, how they got here, or what brought them) before the conversation gets going. {choice_hint}For each line, specify:
1. character_name - the name of the speaking character, exactly as in the list.
2. text - the text of the line.
3. is_thought - boolean. True if the protagonist's line is their inner thoughts (not spoken aloud, shown as an inner monologue); for speech out loud and for all other characters it is always false.
Answer STRICTLY as JSON matching this schema:
{
  "dialogue_lines": [
    {
      "character_name": string,
      "text": string,
      "is_thought": boolean
    }
  ]
}{protagonist_block}{assets_block}
{russian_note}""",
        """Novel characters:
{cast}{asset_catalog}{story_context_block}{current_outfits_block}{previous_scene_block}{previous_lines_block}{used_phrases_block}
Scene: {scene_title}
Scene description: {scene_description}
This scene takes place at: {place_time}.
Scene participants: {scene_participants}""",
    ),
    "story_context": (
        """You are the editor of an interactive visual novel and maintain the story recap from which the following scenes will be generated. Based on the previous recap and the new scene's dialogue, return ONLY the changes:
- remove_facts - the numbers of facts from the previous recap that are outdated, no longer important to the plot, or absorbed by new ones;
- add_facts - new facts from this scene that matter for the plot going forward (events, decisions, secrets, promises, relationships, objects, where characters are), each a single short sentence up to 120 characters. A fact counts as a duplicate if it repeats the meaning of an existing fact, even in different words — do not add such facts. If a new fact absorbs an existing one, add the number of the absorbed one to remove_facts. No more than {max_key_facts} facts should remain after the changes;
- characters - only characters for whom something changed or who appear for the first time: {outfit_instruction} state - physical and emotional state, up to 80 characters. Empty string means no changes.
Answer STRICTLY as JSON matching this schema:
{
  "remove_facts": [int],
  "add_facts": [string],
  "characters": [
    {
      "name": string,
      "outfit": string,
      "state": string
    }
  ]
}
{russian_note}""",
        """Story title: {title}
Characters:
{cast}

Previous recap:
{previous_recap}

New scene: {scene_title}
Scene description: {scene_description}
Scene dialogue:
{dialogue}""",
    ),
    "branch_roadmap": (
        """You are a screenwriter for interactive visual novels. Create the roadmap of an ALTERNATIVE branch of the story: the protagonist made a different choice, and now the story diverges and leads to its own ending. The branch is linear — no branches and no player choices. Decide the number of steps yourself — usually 3 to 6; keep it tight, each step moves the plot toward this branch's own resolution. For each step, specify:
1. title - a short title.
2. event - ONE completed event/beat of this step (fits into 1-2 scenes).
3. conflict - what makes this event hard for the protagonist.
4. change - what changes for the protagonist by the end of the step.
5. scenes_count - 1 or 2 (the final step may have 2 or 3).
6. location_slug - ONLY from the location list (empty string if no list).
7. time_of_day - ONLY from the time-of-day list (empty string if no list).
8. day - integer from the branch's start day, non-decreasing.
Build event/conflict/change only on the characters from the list below; do not introduce characters who are not in the list. Do not contradict the story so far. The branch ends with a real resolution, not a cliffhanger cut.
Answer STRICTLY as JSON matching this schema:
{
  "roadmap": [
    {
      "title": string,
      "event": string,
      "conflict": string,
      "change": string,
      "scenes_count": integer,
      "location_slug": string,
      "time_of_day": string,
      "day": integer
    }
  ]
}
{russian_note}""",
        """Story title: {title}
Narrative tone: {tone}
Story description: {description}

Choice point step: {fork_title}
Choice stakes: {choice_stakes}
Chosen branch: {choice_text}
Branch direction: {branch_direction}
Start day: {start_day}{place_time_catalog}{characters_block}""",
    ),
    "scene_validator": (
        """You are the editor of an interactive visual novel. Check whether the generated scene matches the current roadmap step BY MEANING. Judge strictly on three axes:
1. theme_match — theme/event: the scene moves the plot toward the step's event, carries the step's conflict, and reaches the step's change, rather than replaying what already passed or fulfilling the event of another step;
2. location_match — place: the scene takes place in the location set by the step (or logically continues it), not in another location;
3. time_match — time: the scene takes place in the day/stage set by the step (or logically follows from the story recap), rather than drifting into another day/stage.
The step's and scene's location and day are set explicitly; if they differ — set false on the corresponding axis. If the step's place or time is not set — set true on that axis, do not invent a mismatch. Treat only an explicit mismatch as a discrepancy.
Answer STRICTLY as JSON matching this schema:
{
  "theme_match": boolean,
  "location_match": boolean,
  "time_match": boolean,
  "reason": string
}
reason — a short explanation of the discrepancy on the axes where there is one; empty string if everything matches.
{russian_note}""",
        """Roadmap step: {step_title}
Step event: {step_event}
Step conflict: {step_conflict}
Step change: {step_change}
Step location: {step_location}
Step time of day: {step_time_of_day}
Step day: {step_day}{story_context_block}
Scene: {scene_title}
Scene description: {scene_description}
Scene location: {scene_location}
Scene time of day: {scene_time_of_day}
Scene day: {scene_day}""",
    ),
}


def upgrade() -> None:
    """Upgrade schema."""
    # 1. novels.prompt_variant — набор промптов (default, nsfw, …).
    op.add_column(
        'novels',
        sa.Column(
            'prompt_variant',
            sa.String(),
            nullable=False,
            server_default='default',
        ),
    )

    # 2. prompts — версионируемые шаблоны промптов (append-only).
    op.create_table(
        'prompts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('variant', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('system_template', sa.Text(), nullable=False),
        sa.Column('user_template', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', 'variant', 'version', name='uq_prompts_key_variant_version'),
    )
    op.create_index(op.f('ix_prompts_id'), 'prompts', ['id'], unique=False)
    op.create_index(op.f('ix_prompts_key'), 'prompts', ['key'], unique=False)
    op.create_index(op.f('ix_prompts_variant'), 'prompts', ['variant'], unique=False)

    # 3. Сид версии 1 (вариант default).
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
    op.bulk_insert(
        prompts_table,
        [
            {
                'key': key,
                'variant': 'default',
                'version': 1,
                'system_template': system,
                'user_template': user,
                'is_active': True,
                'created_at': now,
                'updated_at': now,
            }
            for key, (system, user) in _DEFAULT_PROMPTS.items()
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_prompts_variant'), table_name='prompts')
    op.drop_index(op.f('ix_prompts_key'), table_name='prompts')
    op.drop_index(op.f('ix_prompts_id'), table_name='prompts')
    op.drop_table('prompts')
    op.drop_column('novels', 'prompt_variant')
