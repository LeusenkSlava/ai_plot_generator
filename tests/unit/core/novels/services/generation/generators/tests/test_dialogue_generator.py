from types import SimpleNamespace

import pytest

from src.core.codex.models import BackgroundTags, Tag, TagKind, TagType, VisualMatch
from src.core.novels.exceptions import GenerationError
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.assets import SceneAssetService
from src.core.novels.services.generation.generators.dialogue import DialogueGenerator
from tests.factories import (
    background_domain,
    dialogue_line_domain,
    dialogue_line_payload,
    novel_character_domain,
    novel_domain,
    roadmap_domain,
    scene_domain,
    valid_dialogue_llm_payload,
)
from tests.fakes.outbound.ai.generator import FakeGenerator
from tests.fakes.outbound.codex.client import FakeCodexService
from tests.fakes.outbound.database.repositories.character_repository import (
    FakeCharacterRepository,
)
from tests.fakes.outbound.database.repositories.dialogue_line_repository import (
    FakeDialogueLineRepository,
)
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)
from tests.fakes.outbound.database.repositories.roadmap_repository import (
    FakeRoadmapRepository,
)
from tests.fakes.outbound.database.repositories.scene_repository import (
    FakeSceneRepository,
)
from tests.unit.outbound.codex.factories import (
    emotion_domain,
    outfit_domain,
    outfit_with_emotions_domain,
    sprite_domain,
)

# ---------------------------------------------------------------------------
# Кодекс-сценарий: одна вселенная, два персонажа с полным набором ассетов.
# ---------------------------------------------------------------------------

ALICE_CODEX_ID = 10
BOB_CODEX_ID = 20


def seed_codex(codex: FakeCodexService) -> None:
    angry = Tag(
        id=1, type=TagType.EMOTION, slug="angry", name="Злость", kind=TagKind.BASE
    )
    soft = Tag(
        id=2, type=TagType.EMOTION, slug="soft", name="Мягко", kind=TagKind.MODIFIER
    )
    calm = Tag(
        id=3, type=TagType.EMOTION, slug="calm", name="Спокойствие", kind=TagKind.BASE
    )
    red_dress = Tag(
        id=4, type=TagType.OUTFIT_STYLE, slug="red-dress", name="Красное платье"
    )
    armor = Tag(id=5, type=TagType.OUTFIT_STYLE, slug="armor", name="Доспех")

    codex.add_backgrounds(
        1,
        [
            background_domain(
                id=1, universe_id=1, slug="forest", description="Лес",
                asset_key="bg/forest.png", sound_asset_key="sounds/forest.ogg",
            )
        ],
    )
    codex.add_background_tags(
        1,
        BackgroundTags(
            base=[Tag(id=6, type=TagType.LOCATION, slug="forest", name="Лес")],
            modifiers=[Tag(id=7, type=TagType.TIME_OF_DAY, slug="day", name="День")],
        ),
    )

    codex.add_outfits_with_emotions(
        ALICE_CODEX_ID,
        [
            outfit_with_emotions_domain(
                outfit=outfit_domain(
                    id=200, sprite_id=100, slug="red-dress", name="Красное платье",
                    asset_key="outfits/red-dress.png", tags=[red_dress],
                ),
                emotions=[
                    emotion_domain(
                        id=300, sprite_id=100, slug="angry", name="Злость",
                        asset_key="emotions/alice-angry.png", tags=[angry],
                    ),
                    emotion_domain(
                        id=301, sprite_id=100, slug="soft", name="Мягко",
                        asset_key="emotions/alice-soft.png", tags=[soft],
                    ),
                ],
            )
        ],
    )
    codex.add_outfits_with_emotions(
        BOB_CODEX_ID,
        [
            outfit_with_emotions_domain(
                outfit=outfit_domain(
                    id=201, sprite_id=101, slug="armor", name="Доспех",
                    asset_key="outfits/armor.png", tags=[armor],
                ),
                emotions=[
                    emotion_domain(
                        id=302, sprite_id=101, slug="calm", name="Спокойствие",
                        asset_key="emotions/bob-calm.png", tags=[calm],
                    ),
                ],
            )
        ],
    )

    alice_sprite = sprite_domain(
        id=100, character_id=ALICE_CODEX_ID, slug="alice-base",
        description="Алиса", asset_key="sprites/alice.png",
    )
    bob_sprite = sprite_domain(
        id=101, character_id=BOB_CODEX_ID, slug="bob-armor",
        description="Боб", asset_key="sprites/bob.png",
    )

    codex.set_match_visual(
        ALICE_CODEX_ID,
        "red-dress",
        ["angry", "soft"],
        VisualMatch(
            sprite_asset_key=alice_sprite.asset_key,
            outfit_asset_key="outfits/red-dress.png",
            emotion_asset_key="emotions/alice-angry.png",
        ),
    )
    codex.set_match_visual(
        BOB_CODEX_ID,
        "armor",
        ["calm"],
        VisualMatch(
            sprite_asset_key=bob_sprite.asset_key,
            outfit_asset_key="outfits/armor.png",
            emotion_asset_key="emotions/bob-calm.png",
        ),
    )


def _default_payload() -> dict:
    return valid_dialogue_llm_payload(
        dialogue_line_payload(
            character_name="Алиса",
            text="Я найду брата!",
            background_base_tag="forest",
            background_modifier_tags=[],
            emotion_base_tag="angry",
            emotion_modifier_tags=["soft"],
            outfit_tag="red-dress",
        ),
        dialogue_line_payload(
            character_name="Боб",
            text="Я пойду с тобой.",
            background_base_tag="forest",
            background_modifier_tags=[],
            emotion_base_tag="calm",
            emotion_modifier_tags=[],
            outfit_tag="armor",
        ),
    )


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------


@pytest.fixture
def novel_repository() -> FakeNovelRepository:
    return FakeNovelRepository()


@pytest.fixture
def scene_repository() -> FakeSceneRepository:
    return FakeSceneRepository()


@pytest.fixture
def roadmap_repository() -> FakeRoadmapRepository:
    return FakeRoadmapRepository()


@pytest.fixture
def character_repository() -> FakeCharacterRepository:
    return FakeCharacterRepository()


@pytest.fixture
def dialogue_line_repository() -> FakeDialogueLineRepository:
    return FakeDialogueLineRepository()


@pytest.fixture
def novel_service(novel_repository: FakeNovelRepository) -> NovelService:
    return NovelService(novel_repository)


@pytest.fixture
def scene_service(scene_repository: FakeSceneRepository) -> SceneService:
    return SceneService(scene_repository)


@pytest.fixture
def roadmap_service(roadmap_repository: FakeRoadmapRepository) -> RoadmapService:
    return RoadmapService(roadmap_repository)


@pytest.fixture
def character_service(character_repository: FakeCharacterRepository) -> CharacterService:
    return CharacterService(character_repository)


@pytest.fixture
def dialogue_line_service(
    dialogue_line_repository: FakeDialogueLineRepository,
) -> DialogueLineService:
    return DialogueLineService(dialogue_line_repository)


@pytest.fixture
def codex() -> FakeCodexService:
    return FakeCodexService()


@pytest.fixture
def generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture
def sut(
    novel_service: NovelService,
    scene_service: SceneService,
    roadmap_service: RoadmapService,
    character_service: CharacterService,
    dialogue_line_service: DialogueLineService,
    codex: FakeCodexService,
    generator: FakeGenerator,
) -> DialogueGenerator:
    return DialogueGenerator(
        novel_service=novel_service,
        scene_service=scene_service,
        roadmap_service=roadmap_service,
        character_service=character_service,
        dialogue_line_service=dialogue_line_service,
        scene_assets=SceneAssetService(codex),
        generator=generator,
    )


@pytest.fixture
def universe_id() -> int | None:
    """По умолчанию новелла без вселенной — Codex не дёргается."""
    return None


@pytest.fixture
async def world(
    universe_id: int | None,
    novel_repository: FakeNovelRepository,
    roadmap_repository: FakeRoadmapRepository,
    scene_repository: FakeSceneRepository,
    character_repository: FakeCharacterRepository,
) -> SimpleNamespace:
    novel = await novel_repository.add(novel_domain(id=None, universe_id=universe_id))
    roadmap = await roadmap_repository.add(
        roadmap_domain(id=None, novel_id=novel.id)
    )
    scene = await scene_repository.add(scene_domain(id=None, roadmap_id=roadmap.id))
    alice = await character_repository.add(
        novel_character_domain(
            id=None, novel_id=novel.id, name="Алиса", role="Ведьма",
            codex_character_id=ALICE_CODEX_ID,
        )
    )
    bob = await character_repository.add(
        novel_character_domain(
            id=None, novel_id=novel.id, name="Боб", role="Рыцарь",
            codex_character_id=BOB_CODEX_ID,
        )
    )
    return SimpleNamespace(novel=novel, roadmap=roadmap, scene=scene, alice=alice, bob=bob)


@pytest.fixture(autouse=True)
def _default_llm_response(generator: FakeGenerator) -> None:
    """По умолчанию LLM возвращает валидный диалог из двух реплик.

    Тесты могут переопределить поведение через generator.returns(...)/raises(...):
    очередь в FakeGenerator имеет приоритет над always_returns.
    """
    generator.always_returns(_default_payload())


# ---------------------------------------------------------------------------
# Без universe_id — Codex не дёргается, ассеты не подбираются
# ---------------------------------------------------------------------------


class TestGenerateWithoutUniverse:
    async def test_codex_not_called(self, sut, codex, world):
        await sut.generate(scene_id=world.scene.id)

        assert codex.calls == []

    async def test_lines_saved_in_order(self, sut, dialogue_line_repository, world):
        result = await sut.generate(scene_id=world.scene.id)

        assert [line.text for line in result] == ["Я найду брата!", "Я пойду с тобой."]
        assert [line.order for line in result] == [1, 2]
        assert [line.is_final_for_scene for line in result] == [False, True]
        assert dialogue_line_repository.saved == result

    async def test_asset_keys_are_none_without_universe(self, sut, world):
        result = await sut.generate(scene_id=world.scene.id)

        for line in result:
            assert line.background_asset_key is None
            assert line.sprite_asset_key is None
            assert line.outfit_asset_key is None
            assert line.emotion_asset_key is None

    async def test_prompt_is_two_messages(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        assert generator.last_prompt_roles == ["system", "user"]

    async def test_prompt_has_cast_and_scene(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        generator.assert_system_contains("screenwriter for interactive visual novels")
        user_prompt = generator.last_user_prompt
        assert "Novel characters:" in user_prompt
        assert "Алиса" in user_prompt
        assert "Боб" in user_prompt
        assert "Scene participants:" in user_prompt
        assert world.scene.title in user_prompt
        assert world.scene.description in user_prompt

    async def test_prompt_has_no_codex_catalog(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        user_prompt = generator.last_user_prompt
        assert "Asset catalog" not in user_prompt
        assert "Backgrounds (background_base_tag" not in user_prompt

    async def test_llm_called_exactly_once(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        assert generator.call_count == 1

    async def test_prompt_forbids_moral_endings(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        generator.assert_system_contains(
            "concluding thought",
            "scene's final line",
        )

    async def test_full_cast_in_head_participants_separate(
        self, sut, generator, world, scene_repository
    ):
        """Полный каст всегда в голове промпта, участники сцены — отдельным блоком."""
        scene = await scene_repository.add(
            scene_domain(
                id=None,
                roadmap_id=world.roadmap.id,
                character_ids=[world.alice.id],
            )
        )
        # В сцене только Алиса — реплики только за неё, иначе проверка каста упадёт.
        generator.returns(
            valid_dialogue_llm_payload(
                dialogue_line_payload(character_name="Алиса", text="Я найду брата!")
            )
        )

        await sut.generate(scene_id=scene.id)

        user_prompt = generator.last_user_prompt
        assert "Novel characters:" in user_prompt
        # Боба нет в сцене, но он остаётся в полном касте в голове промпта.
        assert "Боб" in user_prompt
        assert "Scene participants: Алиса" in user_prompt
        assert "Scene participants: Алиса, Боб" not in user_prompt


# ---------------------------------------------------------------------------
# С universe_id — Codex загружает ассеты и подбирает их под реплики
# ---------------------------------------------------------------------------


class TestGenerateWithUniverse:
    @pytest.fixture
    def universe_id(self) -> int:
        return 1

    @pytest.fixture(autouse=True)
    def _seed_codex(self, codex: FakeCodexService) -> None:
        seed_codex(codex)

    async def test_codex_loads_assets(self, sut, codex, world):
        await sut.generate(scene_id=world.scene.id)

        # Фаза загрузки ассетов: фон + каталог нарядов (параллельно)
        assert codex.calls[:2] == [
            ("get_background_tags", 1),
            ("get_outfits_with_emotions_batch", [ALICE_CODEX_ID, BOB_CODEX_ID]),
        ]

    async def test_assets_resolved(self, sut, world):
        result = await sut.generate(scene_id=world.scene.id)

        assert len(result) == 2
        alice_line, bob_line = result

        assert alice_line.character_id == world.alice.id
        assert alice_line.background_asset_key == "bg/forest.png"
        assert alice_line.sound_asset_key == "sounds/forest.ogg"
        assert alice_line.sprite_asset_key == "sprites/alice.png"
        assert alice_line.outfit_asset_key == "outfits/red-dress.png"
        assert alice_line.emotion_asset_key == "emotions/alice-angry.png"
        assert alice_line.is_final_for_scene is False

        assert bob_line.character_id == world.bob.id
        assert bob_line.background_asset_key == "bg/forest.png"
        assert bob_line.sound_asset_key == "sounds/forest.ogg"
        assert bob_line.sprite_asset_key == "sprites/bob.png"
        assert bob_line.outfit_asset_key == "outfits/armor.png"
        assert bob_line.emotion_asset_key == "emotions/bob-calm.png"
        assert bob_line.is_final_for_scene is True

    async def test_prompt_contains_catalog(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        user_prompt = generator.last_user_prompt
        assert "Asset catalog" in user_prompt
        assert "Backgrounds (background_base_tag" in user_prompt
        generator.assert_system_contains(
            "background_base_tag",
            "outfit_tag",
            "emotion_base_tag",
            "emotion_modifier_tags",
        )

    async def test_prompt_has_no_sprite_slug(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        generator.assert_system_not_contains("sprite_slug")

    async def test_catalog_groups_emotions_by_outfit(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        user_prompt = generator.last_user_prompt
        assert "Outfits of character Алиса" in user_prompt
        assert "red-dress" in user_prompt
        assert "angry=Злость" in user_prompt
        assert "soft=Мягко" in user_prompt

    async def test_match_visual_called(self, sut, codex, world):
        await sut.generate(scene_id=world.scene.id)

        assert (
            "match_visual",
            ALICE_CODEX_ID,
            "red-dress",
            ["angry", "soft"],
        ) in codex.calls
        assert (
            "match_visual",
            BOB_CODEX_ID,
            "armor",
            ["calm"],
        ) in codex.calls

    async def test_sprite_asset_key_from_match_visual(self, sut, codex, world):
        codex.set_match_visual(
            ALICE_CODEX_ID,
            "red-dress",
            ["angry", "soft"],
            VisualMatch(
                sprite_asset_key="sprites/alice-close.png",
                outfit_asset_key="outfits/red-dress.png",
                emotion_asset_key="emotions/alice-angry.png",
            ),
        )

        result = await sut.generate(scene_id=world.scene.id)

        assert result[0].sprite_asset_key == "sprites/alice-close.png"


# ---------------------------------------------------------------------------
# Контекст промпта: story_context, предыдущие реплики, текущие наряды
# ---------------------------------------------------------------------------


class TestPromptContext:
    @pytest.fixture
    def universe_id(self) -> int:
        return 1

    @pytest.fixture(autouse=True)
    def _seed_codex(self, codex: FakeCodexService) -> None:
        seed_codex(codex)

    async def test_story_context_in_prompt(self, sut, generator, world):
        await sut.generate(
            scene_id=world.scene.id,
            story_context="Алиса потеряла брата в лесу.",
        )

        user_prompt = generator.last_user_prompt
        assert "Story so far" in user_prompt
        assert "Алиса потеряла брата в лесу." in user_prompt

    async def test_previous_lines_in_prompt(self, sut, generator, world):
        previous = [
            dialogue_line_domain(character_id=world.alice.id, text="Где он?", scene_id=999),
            dialogue_line_domain(character_id=world.bob.id, text="Не знаю.", scene_id=999),
        ]

        await sut.generate(scene_id=world.scene.id, previous_lines=previous)

        user_prompt = generator.last_user_prompt
        assert "Last lines of the previous scene" in user_prompt
        assert "Алиса: Где он?" in user_prompt
        assert "Боб: Не знаю." in user_prompt

    async def test_current_outfits_in_prompt(
        self, sut, generator, dialogue_line_repository, world
    ):
        dialogue_line_repository.set_last_outfits(
            {world.alice.id: "outfits/red-dress.png"}
        )

        await sut.generate(scene_id=world.scene.id)

        user_prompt = generator.last_user_prompt
        assert "Current character outfits" in user_prompt
        assert "Алиса: outfit_tag red-dress" in user_prompt

    async def test_no_context_by_default(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        user_prompt = generator.last_user_prompt
        assert "Story so far" not in user_prompt
        assert "Last lines of the previous scene" not in user_prompt
        assert "Current character outfits" not in user_prompt


# ---------------------------------------------------------------------------
# Тонкости подбора ассетов
# ---------------------------------------------------------------------------


class TestAssetMatching:
    @pytest.fixture
    def universe_id(self) -> int:
        return 1

    @pytest.fixture(autouse=True)
    def _seed_codex(self, codex: FakeCodexService) -> None:
        seed_codex(codex)

    async def test_no_visual_match_sets_none(self, sut, codex, world):
        """Отсутствие совпадения в Codex оставляет все asset_key пустыми."""
        codex.set_match_visual(ALICE_CODEX_ID, "red-dress", ["angry", "soft"], None)

        result = await sut.generate(scene_id=world.scene.id)

        alice_line = result[0]
        assert alice_line.sprite_asset_key is None
        assert alice_line.outfit_asset_key is None
        assert alice_line.emotion_asset_key is None

    async def test_visual_unavailable_does_not_raise(self, sut, codex, world):
        codex.fail_on("match_visual")

        result = await sut.generate(scene_id=world.scene.id)

        # генерация продолжается, визуал не подобран
        assert result[0].emotion_asset_key is None
        assert result[0].sprite_asset_key is None
        assert result[0].outfit_asset_key is None

    async def test_unresolved_background_slug_is_none(self, sut, generator, world):
        generator.returns(
            valid_dialogue_llm_payload(
                dialogue_line_payload(
                    character_name="Алиса",
                    text="Где же он?",
                    background_base_tag="nonexistent",
                    background_modifier_tags=[],
                    emotion_base_tag="angry",
                    emotion_modifier_tags=[],
                    outfit_tag="red-dress",
                )
            )
        )

        result = await sut.generate(scene_id=world.scene.id)

        assert result[0].background_asset_key is None


# ---------------------------------------------------------------------------
# Починка эмоций при генерации: наряд резолвился, а эмоция — нет
# ---------------------------------------------------------------------------


class TestMissingEmotionFix:
    @pytest.fixture
    def universe_id(self) -> int:
        return 1

    @pytest.fixture(autouse=True)
    def _seed_codex(self, codex: FakeCodexService) -> None:
        seed_codex(codex)

    async def test_second_call_repairs_missing_emotion(
        self, sut, generator, codex, world
    ):
        # Первый подбор: наряд резолвится, а эмоция — нет (LLM выдумал emotion-тег).
        codex.set_match_visual(
            ALICE_CODEX_ID,
            "red-dress",
            ["angry", "soft"],
            VisualMatch(
                sprite_asset_key="sprites/alice.png",
                outfit_asset_key="outfits/red-dress.png",
                emotion_asset_key=None,
            ),
        )
        # Повторный подбор с корректным тегом возвращает эмоцию.
        codex.set_match_visual(
            ALICE_CODEX_ID,
            "red-dress",
            ["angry"],
            VisualMatch(
                sprite_asset_key="sprites/alice.png",
                outfit_asset_key="outfits/red-dress.png",
                emotion_asset_key="emotions/alice-angry.png",
            ),
        )
        generator.returns(_default_payload()).returns(
            {
                "lines": [
                    {"index": 1, "emotion_base_tag": "angry", "emotion_modifier_tags": []}
                ]
            }
        )

        result = await sut.generate(scene_id=world.scene.id)

        assert generator.call_count == 2
        assert result[0].emotion_asset_key == "emotions/alice-angry.png"

    async def test_no_repair_when_all_emotions_resolve(
        self, sut, generator, codex, world
    ):
        result = await sut.generate(scene_id=world.scene.id)

        assert generator.call_count == 1
        assert result[0].emotion_asset_key == "emotions/alice-angry.png"

    async def test_fallback_when_repair_returns_invalid_tag(
        self, sut, generator, codex, world
    ):
        codex.set_match_visual(
            ALICE_CODEX_ID,
            "red-dress",
            ["angry", "soft"],
            VisualMatch(
                sprite_asset_key="sprites/alice.png",
                outfit_asset_key="outfits/red-dress.png",
                emotion_asset_key=None,
            ),
        )
        codex.set_match_visual(
            ALICE_CODEX_ID,
            "red-dress",
            ["angry"],
            VisualMatch(
                sprite_asset_key="sprites/alice.png",
                outfit_asset_key="outfits/red-dress.png",
                emotion_asset_key="emotions/alice-angry.png",
            ),
        )
        # LLM снова вернул невалидный slug — падаем на детерминированный запасной.
        generator.returns(_default_payload()).returns(
            {
                "lines": [
                    {"index": 1, "emotion_base_tag": "serious", "emotion_modifier_tags": []}
                ]
            }
        )

        result = await sut.generate(scene_id=world.scene.id)

        assert generator.call_count == 2
        assert result[0].emotion_asset_key == "emotions/alice-angry.png"


# ---------------------------------------------------------------------------
# Точечный ремонт и ретрай (новый пайплайн generate)
# ---------------------------------------------------------------------------


class TestRepairFlow:
    async def test_unknown_name_repaired_by_llm(self, sut, generator, world):
        """Неизвестное имя ремапится одним дешёвым запросом, без полного ретрая."""
        generator.returns(
            valid_dialogue_llm_payload(
                dialogue_line_payload(character_name="Незнакомец", text="Кто я?")
            )
        ).returns(
            {"fixes": [{"index": 1, "character_name": "Алиса", "text": "Кто я?"}]}
        )

        result = await sut.generate(scene_id=world.scene.id)

        assert [line.character_id for line in result] == [world.alice.id]
        assert result[0].text == "Кто я?"
        assert generator.call_count == 2  # основной вызов + точечный ремонт

    async def test_duplicate_lines_deduped_and_reordered(self, sut, generator, world):
        """Точные дубли удаляются; order/is_final_for_scene считаются по финальному списку."""
        generator.returns(
            valid_dialogue_llm_payload(
                dialogue_line_payload(character_name="Алиса", text="Я найду брата!"),
                dialogue_line_payload(character_name="Боб", text="Я пойду с тобой."),
                dialogue_line_payload(character_name="Алиса", text="Я найду брата!"),
            )
        )

        result = await sut.generate(scene_id=world.scene.id)

        assert [line.text for line in result] == ["Я найду брата!", "Я пойду с тобой."]
        assert [line.order for line in result] == [1, 2]
        assert [line.is_final_for_scene for line in result] == [False, True]
        assert generator.call_count == 1  # дедуп детерминированный, без LLM

    async def test_truncated_end_completed(self, sut, generator, world):
        """Обрыв последней реплики дописывается дешёвым запросом, остальные не трогаются."""
        generator.returns(
            valid_dialogue_llm_payload(
                dialogue_line_payload(character_name="Алиса", text="Я найду брата!"),
                dialogue_line_payload(character_name="Боб", text="Мы пойдём вместе и"),
            )
        ).returns(
            {
                "fixes": [
                    {
                        "index": 1,
                        "character_name": "Боб",
                        "text": "Мы пойдём вместе и найдём его.",
                    }
                ]
            }
        )

        result = await sut.generate(scene_id=world.scene.id)

        assert result[0].text == "Я найду брата!"
        assert result[-1].text == "Мы пойдём вместе и найдём его."
        assert result[-1].is_final_for_scene is True
        assert generator.call_count == 2

    async def test_retry_recovers_with_feedback(self, sut, generator, world):
        """Первый ответ битый (пустой), повтор с feedback даёт валидный диалог."""
        generator.returns({"dialogue_lines": []}).returns(_default_payload())

        result = await sut.generate(scene_id=world.scene.id)

        assert [line.text for line in result] == ["Я найду брата!", "Я пойду с тобой."]
        assert generator.call_count == 2
        # Второму вызову добавлено user-сообщение с причиной.
        assert generator.calls[1][-1]["role"] == "user"
        assert "Reason:" in generator.calls[1][-1]["content"]


# ---------------------------------------------------------------------------
# Ошибки
# ---------------------------------------------------------------------------


class TestGenerateErrors:
    async def test_scene_not_found(self, sut, generator):
        with pytest.raises(GenerationError, match="Scene with id 1 not found"):
            await sut.generate(scene_id=1)

        assert generator.not_called

    async def test_roadmap_not_found(self, sut, scene_repository, generator):
        await scene_repository.add(scene_domain(id=None, roadmap_id=999))

        with pytest.raises(GenerationError, match="Roadmap with id 999 not found"):
            await sut.generate(scene_id=1)

        assert generator.not_called

    async def test_no_characters(
        self,
        sut,
        novel_repository,
        roadmap_repository,
        scene_repository,
        generator,
    ):
        novel = await novel_repository.add(novel_domain(id=None, universe_id=None))
        roadmap = await roadmap_repository.add(
            roadmap_domain(id=None, novel_id=novel.id)
        )
        await scene_repository.add(scene_domain(id=None, roadmap_id=roadmap.id))

        with pytest.raises(GenerationError, match="No characters found"):
            await sut.generate(scene_id=1)

        assert generator.not_called

    async def test_unknown_character_retries_then_raises(self, sut, generator, world):
        """Неизвестное имя не чинится фуззи/LLM — после ретраев GenerationError."""
        generator.always_returns(
            valid_dialogue_llm_payload(
                dialogue_line_payload(character_name="Незнакомец", text="Кто я?")
            )
        )

        with pytest.raises(GenerationError, match="не удалось получить валидный диалог"):
            await sut.generate(scene_id=world.scene.id)

    async def test_generator_returns_no_lines(self, sut, generator, world):
        """Пустой ответ неисправим — полный ретрай, затем GenerationError."""
        generator.always_returns({"dialogue_lines": []})

        with pytest.raises(GenerationError, match="не удалось получить валидный диалог"):
            await sut.generate(scene_id=world.scene.id)

    async def test_generator_missing_lines_key(self, sut, generator, world):
        generator.always_returns({})

        with pytest.raises(GenerationError, match="не удалось получить валидный диалог"):
            await sut.generate(scene_id=world.scene.id)

    async def test_llm_failure_wrapped_in_generation_error(self, sut, generator, world):
        generator.raises(RuntimeError("LLM down"))

        with pytest.raises(GenerationError, match="LLM down"):
            await sut.generate(scene_id=world.scene.id)

    async def test_llm_failure_preserves_cause(self, sut, generator, world):
        original = RuntimeError("LLM down")
        generator.raises(original)

        with pytest.raises(GenerationError) as exc_info:
            await sut.generate(scene_id=world.scene.id)

        assert exc_info.value.__cause__ is original


class TestCodexErrors:
    @pytest.fixture
    def universe_id(self) -> int:
        return 1

    async def test_assets_request_failure_wrapped(self, sut, codex, world, generator):
        codex.fail_on("get_background_tags")

        with pytest.raises(GenerationError, match="Codex assets request failed"):
            await sut.generate(scene_id=world.scene.id)

        assert generator.not_called


# ---------------------------------------------------------------------------
# Главный герой (протагонист): без спрайта, доступны внутренние мысли
# ---------------------------------------------------------------------------


class TestProtagonist:
    @pytest.fixture
    def universe_id(self) -> int:
        return 1

    @pytest.fixture(autouse=True)
    def _seed_codex(self, codex: FakeCodexService) -> None:
        seed_codex(codex)

    @pytest.fixture
    async def protagonist_world(
        self,
        novel_repository: FakeNovelRepository,
        roadmap_repository: FakeRoadmapRepository,
        scene_repository: FakeSceneRepository,
        character_repository: FakeCharacterRepository,
    ) -> SimpleNamespace:
        novel = await novel_repository.add(novel_domain(id=None, universe_id=1))
        roadmap = await roadmap_repository.add(
            roadmap_domain(id=None, novel_id=novel.id)
        )
        scene = await scene_repository.add(scene_domain(id=None, roadmap_id=roadmap.id))
        alice = await character_repository.add(
            novel_character_domain(
                id=None, novel_id=novel.id, name="Алиса", role="Ведьма",
                codex_character_id=ALICE_CODEX_ID, is_protagonist=True,
            )
        )
        bob = await character_repository.add(
            novel_character_domain(
                id=None, novel_id=novel.id, name="Боб", role="Рыцарь",
                codex_character_id=BOB_CODEX_ID,
            )
        )
        return SimpleNamespace(
            novel=novel, roadmap=roadmap, scene=scene, alice=alice, bob=bob
        )

    async def test_protagonist_has_no_sprite_assets(
        self, sut, codex, protagonist_world
    ):
        result = await sut.generate(scene_id=protagonist_world.scene.id)

        alice_line = result[0]
        assert alice_line.character_id == protagonist_world.alice.id
        assert alice_line.background_asset_key == "bg/forest.png"
        assert alice_line.sound_asset_key == "sounds/forest.ogg"
        assert alice_line.sprite_asset_key is None
        assert alice_line.outfit_asset_key is None
        assert alice_line.emotion_asset_key is None

        # ассеты протагониста не загружаются из Codex
        assert codex.calls[:2] == [
            ("get_background_tags", 1),
            ("get_outfits_with_emotions_batch", [BOB_CODEX_ID]),
        ]

    async def test_protagonist_thought_preserved(self, sut, generator, protagonist_world):
        generator.returns(
            valid_dialogue_llm_payload(
                dialogue_line_payload(
                    character_name="Алиса", text="Я не должна бояться.",
                    is_thought=True,
                ),
                dialogue_line_payload(
                    character_name="Боб", text="Ты справишься.", is_thought=True,
                ),
            )
        )

        result = await sut.generate(scene_id=protagonist_world.scene.id)

        assert result[0].is_thought is True
        # is_thought значим только для протагониста — для остальных принудительно false
        assert result[1].is_thought is False
