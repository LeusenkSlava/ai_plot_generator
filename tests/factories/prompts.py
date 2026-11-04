"""Шаблоны промптов для тестов генераторов.

В проде тексты промптов живут в таблице ``prompts`` (их сеют миграции), а
генераторы только подставляют переменные в шаблон через ``PromptCatalog``.
Поэтому тест не может рассчитывать на встроенный текст: он кладёт в
``FakePromptRepository`` свой шаблон с теми же плейсхолдерами, что передаёт
генератор, и проверяет подстановку. Шаблоны ниже намеренно короткие, но
содержат все переменные соответствующего генератора — если генератор перестанет
их передавать, рендер упадёт с ``MissingPromptVariableError``.
"""

from src.core.novels.models import DEFAULT_PROMPT_VARIANT, Prompt, PromptKey
from tests.fakes.outbound.database.repositories.prompt_repository import (
    FakePromptRepository,
)

# ---------------------------------------------------------------------------
# novel
# ---------------------------------------------------------------------------

NOVEL_SYSTEM = (
    "You are a screenwriter for interactive visual novels.\n"
    "{json_instruction}\n"
    "{codex_block}\n"
    "{russian_note}"
)
NOVEL_USER = "{user_prompt}"

# ---------------------------------------------------------------------------
# roadmap
# ---------------------------------------------------------------------------

ROADMAP_SYSTEM = (
    "You are an author of an interactive visual novel.\n"
    "The story is {story_shape}\n"
    "{choice_instructions}\n"
    "Return JSON exactly matching this schema:\n"
    "{schema}\n"
    "{russian_note}"
)
ROADMAP_USER = (
    "User request: {user_prompt}\n\n"
    "Title: {title}\n"
    "Description: {description}\n"
    "Narrative tone: {tone}\n\n"
    "Story shape:\n{shape_block}\n\n"
    "Design brief:\n{design_block}"
    "{place_time_catalog}\n\n"
    "Characters:\n{characters_block}"
)

# ---------------------------------------------------------------------------
# scene
# ---------------------------------------------------------------------------

SCENE_SYSTEM = (
    'You are a scene writer. Return JSON with a "characters" array.\n'
    "{russian_note}"
)
SCENE_USER = (
    "Novel: {title}\n"
    "Tone: {tone}{characters_block}\n\n"
    "Step place and time: {step_place_time}\n"
    "Step: {step_title}\n"
    "Event: {step_event}\n"
    "Conflict: {step_conflict}\n"
    "Change: {step_change}\n"
    "Scene {step_position} of {scenes_count} within the step."
    "{story_context_block}{previous_scenes_block}"
)

# ---------------------------------------------------------------------------
# scene_validator
# ---------------------------------------------------------------------------

SCENE_VALIDATOR_SYSTEM = (
    "You are a continuity checker. Answer STRICTLY as JSON.\n{russian_note}"
)
SCENE_VALIDATOR_USER = (
    "Step: {step_title}\n"
    "Event: {step_event}\n"
    "Conflict: {step_conflict}\n"
    "Change: {step_change}\n"
    "Step location: {step_location}\n"
    "Step time of day: {step_time_of_day}\n"
    "Step day: {step_day}"
    "{story_context_block}\n\n"
    "Scene: {scene_title}\n"
    "{scene_description}\n"
    "Scene location: {scene_location}\n"
    "Scene time of day: {scene_time_of_day}\n"
    "Scene day: {scene_day}"
)

# ---------------------------------------------------------------------------
# dialogue
# ---------------------------------------------------------------------------

DIALOGUE_SYSTEM = (
    "You are a screenwriter for interactive visual novels.\n"
    "{choice_hint}"
    "{protagonist_block}\n"
    "{assets_block}\n"
    "Do not end the scene with a concluding thought: the scene's final line "
    "must keep the story moving.\n"
    "{russian_note}"
)
DIALOGUE_USER = (
    "Novel characters:\n{cast}\n\n"
    "Scene participants: {scene_participants}\n"
    "Scene: {scene_title}\n"
    "{scene_description}\n"
    "Place and time: {place_time}\n"
    "{step_block}"
    "{asset_catalog}"
    "{story_context_block}"
    "{current_outfits_block}"
    "{previous_scene_block}"
    "{previous_lines_block}"
    "{used_phrases_block}"
)

# ---------------------------------------------------------------------------
# story_context
# ---------------------------------------------------------------------------

STORY_CONTEXT_SYSTEM = (
    'You track story continuity. Return JSON with "add_facts", "remove_facts" '
    'and "characters".\n'
    "{outfit_instruction}\n"
    "Keep at most {max_key_facts} facts.\n"
    "{russian_note}"
)
STORY_CONTEXT_USER = (
    "Novel: {title}\n"
    "Cast:\n{cast}\n\n"
    "Previous recap:\n{previous_recap}\n\n"
    "Scene: {scene_title}\n"
    "{scene_description}\n\n"
    "Dialogue:\n{dialogue}"
)


def seed_novel_prompt(
    prompts: FakePromptRepository, variant: str = DEFAULT_PROMPT_VARIANT
) -> Prompt:
    return prompts.set_active(
        PromptKey.NOVEL, variant, system_template=NOVEL_SYSTEM, user_template=NOVEL_USER
    )


def seed_roadmap_prompt(
    prompts: FakePromptRepository, variant: str = DEFAULT_PROMPT_VARIANT
) -> Prompt:
    return prompts.set_active(
        PromptKey.ROADMAP, variant, system_template=ROADMAP_SYSTEM, user_template=ROADMAP_USER
    )


def seed_scene_prompt(
    prompts: FakePromptRepository, variant: str = DEFAULT_PROMPT_VARIANT
) -> Prompt:
    return prompts.set_active(
        PromptKey.SCENE, variant, system_template=SCENE_SYSTEM, user_template=SCENE_USER
    )


def seed_scene_validator_prompt(
    prompts: FakePromptRepository, variant: str = DEFAULT_PROMPT_VARIANT
) -> Prompt:
    return prompts.set_active(
        PromptKey.SCENE_VALIDATOR,
        variant,
        system_template=SCENE_VALIDATOR_SYSTEM,
        user_template=SCENE_VALIDATOR_USER,
    )


def seed_dialogue_prompt(
    prompts: FakePromptRepository, variant: str = DEFAULT_PROMPT_VARIANT
) -> Prompt:
    return prompts.set_active(
        PromptKey.DIALOGUE, variant, system_template=DIALOGUE_SYSTEM, user_template=DIALOGUE_USER
    )


def seed_story_context_prompt(
    prompts: FakePromptRepository, variant: str = DEFAULT_PROMPT_VARIANT
) -> Prompt:
    return prompts.set_active(
        PromptKey.STORY_CONTEXT,
        variant,
        system_template=STORY_CONTEXT_SYSTEM,
        user_template=STORY_CONTEXT_USER,
    )


def seed_all_prompts(
    prompts: FakePromptRepository, variant: str = DEFAULT_PROMPT_VARIANT
) -> FakePromptRepository:
    """Сеет шаблоны всех генераторов, которые встречаются в юнит-тестах."""
    seed_novel_prompt(prompts, variant)
    seed_roadmap_prompt(prompts, variant)
    seed_scene_prompt(prompts, variant)
    seed_scene_validator_prompt(prompts, variant)
    seed_dialogue_prompt(prompts, variant)
    seed_story_context_prompt(prompts, variant)
    return prompts
