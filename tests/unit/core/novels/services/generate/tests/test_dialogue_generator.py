from types import SimpleNamespace

import pytest

from src.core.codex.models import EmotionTags, Tag, TagType
from src.core.novels.exceptions import GenerationError
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generate.dialogue import DialogueGenerator
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
    sprite_domain,
)

# ---------------------------------------------------------------------------
# Кодекс-сценарий: одна вселенная, два персонажа с полным набором ассетов.
# ---------------------------------------------------------------------------

ALICE_CODEX_ID = 10
BOB_CODEX_ID = 20


def seed_codex(codex: FakeCodexService) -> None:
    angry = Tag(id=1, type=TagType.EMOTION, slug="angry", name="Злость")
    soft = Tag(id=2, type=TagType.EMOTION, slug="soft", name="Мягко")
    calm = Tag(id=3, type=TagType.EMOTION, slug="calm", name="Спокойствие")
    red_dress = Tag(
        id=4, type=TagType.OUTFIT_STYLE, slug="red-dress", name="Красное платье"
    )
    armor = Tag(id=5, type=TagType.OUTFIT_STYLE, slug="armor", name="Доспех")

    codex.add_backgrounds(
        1,
        [
            background_domain(
                id=1, universe_id=1, slug="forest", description="Лес",
                asset_key="bg/forest.png",
            )
        ],
    )

    codex.add_emotion_tags(ALICE_CODEX_ID, EmotionTags(base=[angry], modifiers=[soft]))
    codex.add_outfit_tags(ALICE_CODEX_ID, [red_dress])
    codex.add_sprites(
        ALICE_CODEX_ID,
        [
            sprite_domain(
                id=100, character_id=ALICE_CODEX_ID, slug="alice-base",
                description="Алиса", asset_key="sprites/alice.png",
            )
        ],
    )
    codex.add_outfits(
        100,
        [
            outfit_domain(
                id=200, sprite_id=100, slug="red-dress", name="Красное платье",
                asset_key="outfits/red-dress.png", tags=[red_dress],
            )
        ],
    )

    codex.add_emotion_tags(BOB_CODEX_ID, EmotionTags(base=[calm], modifiers=[]))
    codex.add_outfit_tags(BOB_CODEX_ID, [armor])
    codex.add_sprites(
        BOB_CODEX_ID,
        [
            sprite_domain(
                id=101, character_id=BOB_CODEX_ID, slug="bob-armor",
                description="Боб", asset_key="sprites/bob.png",
            )
        ],
    )
    codex.add_outfits(
        101,
        [
            outfit_domain(
                id=201, sprite_id=101, slug="armor", name="Доспех",
                asset_key="outfits/armor.png", tags=[armor],
            )
        ],
    )

    codex.set_match_emotion(
        ALICE_CODEX_ID,
        emotion_domain(
            id=300, sprite_id=100, slug="angry", name="Злость",
            asset_key="emotions/alice-angry.png",
        ),
    )
    codex.set_match_emotion(
        BOB_CODEX_ID,
        emotion_domain(
            id=301, sprite_id=101, slug="calm", name="Спокойствие",
            asset_key="emotions/bob-calm.png",
        ),
    )
    codex.set_match_outfit(
        100, "red-dress",
        outfit_domain(
            id=200, sprite_id=100, slug="red-dress", name="Красное платье",
            asset_key="outfits/red-dress.png", tags=[red_dress],
        ),
    )
    codex.set_match_outfit(
        101, "armor",
        outfit_domain(
            id=201, sprite_id=101, slug="armor", name="Доспех",
            asset_key="outfits/armor.png", tags=[armor],
        ),
    )


def _default_payload() -> dict:
    return valid_dialogue_llm_payload(
        dialogue_line_payload(
            character_name="Алиса",
            text="Я найду брата!",
            background_slug="forest",
            sprite_slug="alice-base",
            emotion_base_tag="angry",
            emotion_modifier_tags=["soft"],
            outfit_tag="red-dress",
        ),
        dialogue_line_payload(
            character_name="Боб",
            text="Я пойду с тобой.",
            background_slug="forest",
            sprite_slug="bob-armor",
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
        codex_service=codex,
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

        generator.assert_system_contains("сценарист интерактивных визуальных новелл")
        user_prompt = generator.last_user_prompt
        assert "Алиса" in user_prompt
        assert "Боб" in user_prompt
        assert world.scene.title in user_prompt
        assert world.scene.description in user_prompt

    async def test_prompt_has_no_codex_catalog(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        user_prompt = generator.last_user_prompt
        assert "Каталог ассетов" not in user_prompt
        assert "Фоны (background_slug)" not in user_prompt

    async def test_llm_called_exactly_once(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        assert generator.call_count == 1


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

        # Фаза загрузки ассетов детерминирована (фон -> персонажи по id)
        assert codex.calls[:9] == [
            ("get_backgrounds", 1),
            ("get_emotion_tags", ALICE_CODEX_ID),
            ("get_outfit_tags", ALICE_CODEX_ID),
            ("get_sprites", ALICE_CODEX_ID),
            ("get_outfits", 100),
            ("get_emotion_tags", BOB_CODEX_ID),
            ("get_outfit_tags", BOB_CODEX_ID),
            ("get_sprites", BOB_CODEX_ID),
            ("get_outfits", 101),
        ]

    async def test_assets_resolved(self, sut, world):
        result = await sut.generate(scene_id=world.scene.id)

        assert len(result) == 2
        alice_line, bob_line = result

        assert alice_line.character_id == world.alice.id
        assert alice_line.background_asset_key == "bg/forest.png"
        assert alice_line.sprite_asset_key == "sprites/alice.png"
        assert alice_line.outfit_asset_key == "outfits/red-dress.png"
        assert alice_line.emotion_asset_key == "emotions/alice-angry.png"
        assert alice_line.is_final_for_scene is False

        assert bob_line.character_id == world.bob.id
        assert bob_line.background_asset_key == "bg/forest.png"
        assert bob_line.sprite_asset_key == "sprites/bob.png"
        assert bob_line.outfit_asset_key == "outfits/armor.png"
        assert bob_line.emotion_asset_key == "emotions/bob-calm.png"
        assert bob_line.is_final_for_scene is True

    async def test_prompt_contains_catalog(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        user_prompt = generator.last_user_prompt
        assert "Каталог ассетов" in user_prompt
        assert "Фоны (background_slug)" in user_prompt
        generator.assert_system_contains(
            "background_slug",
            "sprite_slug",
            "outfit_tag",
            "emotion_base_tag",
            "emotion_modifier_tags",
        )

    async def test_match_emotion_and_outfit_called(self, sut, codex, world):
        await sut.generate(scene_id=world.scene.id)

        assert ("match_emotion", ALICE_CODEX_ID, ["angry", "soft"], 100) in codex.calls
        assert ("match_emotion", BOB_CODEX_ID, ["calm"], 101) in codex.calls
        assert ("match_outfit", 100, "red-dress") in codex.calls
        assert ("match_outfit", 101, "armor") in codex.calls


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
        assert "Изложение истории" in user_prompt
        assert "Алиса потеряла брата в лесу." in user_prompt

    async def test_previous_lines_in_prompt(self, sut, generator, world):
        previous = [
            dialogue_line_domain(character_id=world.alice.id, text="Где он?", scene_id=999),
            dialogue_line_domain(character_id=world.bob.id, text="Не знаю.", scene_id=999),
        ]

        await sut.generate(scene_id=world.scene.id, previous_lines=previous)

        user_prompt = generator.last_user_prompt
        assert "Последние реплики предыдущей сцены" in user_prompt
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
        assert "Текущие наряды персонажей" in user_prompt
        assert "Алиса: outfit_tag red-dress" in user_prompt

    async def test_no_context_by_default(self, sut, generator, world):
        await sut.generate(scene_id=world.scene.id)

        user_prompt = generator.last_user_prompt
        assert "Изложение истории" not in user_prompt
        assert "Последние реплики предыдущей сцены" not in user_prompt
        assert "Текущие наряды персонажей" not in user_prompt


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

    async def test_final_sprite_taken_from_emotion(self, sut, codex, world):
        """match_emotion может вернуть эмоцию на другом спрайте — спрайт берём из неё."""
        close_sprite = sprite_domain(
            id=102, character_id=ALICE_CODEX_ID, slug="alice-close",
            description="Алиса крупно", asset_key="sprites/alice-close.png",
        )
        codex.add_sprites(
            ALICE_CODEX_ID,
            [
                sprite_domain(
                    id=100, character_id=ALICE_CODEX_ID, slug="alice-base",
                    description="Алиса", asset_key="sprites/alice.png",
                ),
                close_sprite,
            ],
        )
        codex.set_match_emotion(
            ALICE_CODEX_ID,
            emotion_domain(
                id=310, sprite_id=102, slug="angry", name="Злость",
                asset_key="emotions/alice-angry-close.png",
            ),
        )

        result = await sut.generate(scene_id=world.scene.id)

        alice_line = result[0]
        assert alice_line.sprite_asset_key == "sprites/alice-close.png"
        assert alice_line.emotion_asset_key == "emotions/alice-angry-close.png"

    async def test_no_emotion_falls_back_to_llm_sprite(self, sut, codex, world):
        codex.set_match_emotion(ALICE_CODEX_ID, None)

        result = await sut.generate(scene_id=world.scene.id)

        alice_line = result[0]
        assert alice_line.emotion_asset_key is None
        # спрайт берётся из выбора LLM, а не из эмоции
        assert alice_line.sprite_asset_key == "sprites/alice.png"

    async def test_emotion_unavailable_does_not_raise(self, sut, codex, world):
        codex.fail_on("match_emotion")

        result = await sut.generate(scene_id=world.scene.id)

        # генерация продолжается, эмоция не подобрана, спрайт — из LLM
        assert result[0].emotion_asset_key is None
        assert result[0].sprite_asset_key == "sprites/alice.png"

    async def test_unresolved_background_slug_is_none(self, sut, generator, world):
        generator.returns(
            valid_dialogue_llm_payload(
                dialogue_line_payload(
                    character_name="Алиса",
                    text="Где же он?",
                    background_slug="nonexistent",
                    sprite_slug="alice-base",
                    emotion_base_tag="angry",
                    emotion_modifier_tags=[],
                    outfit_tag="red-dress",
                )
            )
        )

        result = await sut.generate(scene_id=world.scene.id)

        assert result[0].background_asset_key is None


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

    async def test_unknown_character(self, sut, generator, world):
        generator.returns(
            valid_dialogue_llm_payload(
                dialogue_line_payload(character_name="Незнакомец", text="Кто я?")
            )
        )

        with pytest.raises(GenerationError, match="unknown character 'Незнакомец'"):
            await sut.generate(scene_id=world.scene.id)

    async def test_generator_returns_no_lines(self, sut, generator, world):
        generator.returns({"dialogue_lines": []})

        with pytest.raises(GenerationError, match="no dialogue lines"):
            await sut.generate(scene_id=world.scene.id)

    async def test_generator_missing_lines_key(self, sut, generator, world):
        generator.returns({})

        with pytest.raises(GenerationError, match="no dialogue lines"):
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
        codex.fail_on("get_backgrounds")

        with pytest.raises(GenerationError, match="Codex assets request failed"):
            await sut.generate(scene_id=world.scene.id)

        assert generator.not_called
