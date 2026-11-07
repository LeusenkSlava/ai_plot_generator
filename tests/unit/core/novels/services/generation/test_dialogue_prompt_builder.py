"""Юнит-тесты DialoguePromptBuilder: правила выбора наряда и каталог ассетов."""

from src.core.codex.models import TagKind
from src.core.novels.models import LineKind, Prompt, Roadmap
from src.core.novels.services.generation.assets import SceneAssets, SceneAssetService
from src.core.novels.services.generation.prompts.dialogue import (
    CURRENT_OUTFITS_HEADER,
    OUTFIT_POLICY,
    DialoguePromptBuilder,
    DialoguePromptContext,
)
from tests.factories import (
    dialogue_line_domain,
    novel_character_domain,
    scene_domain,
)
from tests.fakes.outbound.codex.client import FakeCodexService
from tests.unit.outbound.codex.factories import (
    outfit_emotion_domain,
    outfit_with_emotions_domain,
)

SYSTEM_TEMPLATE = "{assets_block}{protagonist_block}{choice_hint}{russian_note}"
USER_TEMPLATE = (
    "{cast}{asset_catalog}{story_context_block}{current_outfits_block}"
    "{scene_title}{scene_description}{place_time}{scene_participants}"
)


def _prompt() -> Prompt:
    return Prompt(
        id=None,
        created_at=None,
        updated_at=None,
        key="dialogue",
        variant="default",
        version=1,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
    )


def _assets() -> SceneAssets:
    return SceneAssets(
        outfits={
            1: [
                outfit_with_emotions_domain(
                    outfit_tag="camp_uniform",
                    name="Форма вожатого",
                    emotions=[
                        outfit_emotion_domain(
                            slug="smile", name="Улыбка", kind=TagKind.BASE
                        ),
                    ],
                ),
                outfit_with_emotions_domain(
                    outfit_tag="swimsuit",
                    name="Купальник",
                    emotions=[
                        outfit_emotion_domain(
                            slug="shy", name="Смущение", kind=TagKind.BASE
                        ),
                    ],
                ),
            ]
        }
    )


def _context(assets: SceneAssets | None) -> DialoguePromptContext:
    alice = novel_character_domain(
        id=1, novel_id=1, name="Алиса", codex_character_id=1, voice_notes="Дерзкая"
    )
    semen = novel_character_domain(
        id=2,
        novel_id=1,
        name="Семён",
        role="Вожатый",
        voice_notes="Ироничный",
        is_protagonist=True,
    )
    scene = scene_domain(
        id=1,
        roadmap_id=1,
        title="Свои среди чужих",
        description="Ночной пляж, костёр, вожатые уже собрались.",
        location_slug="beach",
        time_of_day="night",
        day=1,
    )
    return DialoguePromptContext(
        scene=scene,
        roadmap=Roadmap(
            id=1,
            created_at=None,
            updated_at=None,
            novel_id=1,
            depth=1,
            title="Шаг 1",
            event="Ночная вечеринка на пляже",
            conflict="Семён чувствует себя лишним",
            change="Вожатые принимают его в круг",
            target_choice=False,
            choice_stakes=None,
            scenes_count=2,
            location_slug="beach",
            time_of_day="night",
            day=1,
        ),
        characters=[alice, semen],
        all_characters=[alice, semen],
        protagonist=semen,
        assets=assets,
        previous_lines=[],
        story_context="Алиса весь вечер была в форме.",
        current_outfits="- Алиса: outfit_tag camp_uniform (Форма)",
        used_phrases=[],
        previous_scene=None,
    )


def _build(assets: SceneAssets | None) -> tuple[str, str]:
    messages = DialoguePromptBuilder(SceneAssetService(FakeCodexService())).build(
        _prompt(), _context(assets)
    )
    return messages[0]["content"], messages[1]["content"]


def test_outfit_policy_allows_scene_change_and_night_beach_swimwear():
    """Наряд меняется на границе сцены, если место/время/событие этого требуют."""
    system, _ = _build(_assets())

    assert OUTFIT_POLICY in system
    assert "does not change between lines and scenes" not in system
    assert "If the scene description does not name the clothes" in system
    assert "at a night beach " in system
    assert "party the natural outfit is swimwear" in system
    assert "must show the new " in system
    assert "clothes" in system


def test_current_outfits_are_previous_scene_not_a_lifetime_constraint():
    """Блок текущих нарядов помечен как «прошлое появление», а не приговор."""
    _, user = _build(_assets())

    assert CURRENT_OUTFITS_HEADER.strip() in user
    assert "Current character outfits (from their last appearance" in user
    assert "if you change them, show it in narration" in user


def test_story_context_does_not_freeze_outfits():
    """Изложение истории не запрещает смену одежды, показанную в сцене."""
    _, user = _build(_assets())

    assert "characters keep the clothes described there" in user
    assert "unless this scene shows them changing" in user


def test_catalog_shows_swimsuit_once_alongside_uniform():
    """Купальник виден в каталоге отдельной строкой, а не тонет в повторах формы."""
    _, user = _build(_assets())

    assert user.count("- camp_uniform (") == 1
    assert user.count("- swimsuit (") == 1
    assert "shy=Смущение" in user


def test_assets_block_uses_scene_level_background_not_per_line():
    """Фон задаётся одним top-level полем, а не на каждую реплику."""
    system, _ = _build(_assets())

    assert "background_modifier_tags" in system
    assert "background_base_tag" not in system


def test_assets_block_describes_background_changes():
    """Инструкция описывает сегментные смены фона внутри сцены."""
    system, _ = _build(_assets())

    assert "background_changes" in system
    assert "at_line" in system
    assert "location_slug" in system
    assert "inside the bus" in system
    assert "narration line" in system


def test_assets_block_forbids_time_of_day_changes():
    """Время суток фиксировано на сцену и не меняется через background_changes."""
    system, _ = _build(_assets())

    assert "time of day is fixed for the whole scene" in system
    assert "do not change it via background_changes either" in system
    assert "do not put a time-of-day tag here either" in system
    assert "set it to null (or omit it) to stay in" in system


def test_render_previous_line_with_location_prefix():
    """Префикс [location] добавляется только при with_location=True."""
    line = dialogue_line_domain(
        id=1, scene_id=1, character_id=2, text="Где он?",
        kind=LineKind.SPEECH, location_slug="beach",
    )

    rendered = DialoguePromptBuilder.render_previous_line(
        line, {2: "Семён"}, with_location=True
    )

    assert rendered == "[beach] Семён: Где он?"


def test_render_previous_line_without_location_is_unchanged():
    """Путь story_context (без with_location) остаётся без префикса локации."""
    line = dialogue_line_domain(
        id=1, scene_id=1, character_id=2, text="Где он?",
        kind=LineKind.SPEECH, location_slug="beach",
    )

    rendered = DialoguePromptBuilder.render_previous_line(line, {2: "Семён"})

    assert rendered == "Семён: Где он?"


def test_render_narration_line_with_location():
    line = dialogue_line_domain(
        id=1, scene_id=1, character_id=None, text="Темно.",
        kind=LineKind.NARRATION, location_slug="beach",
    )

    rendered = DialoguePromptBuilder.render_previous_line(
        line, {}, with_location=True
    )

    assert rendered == "[beach] [narration] Темно."
