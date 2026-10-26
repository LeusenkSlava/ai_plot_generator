import pytest

from src.core.novels.exceptions import GenerationError
from src.core.novels.models import Character, Novel, Roadmap, Scene
from src.core.novels.services.crud import (
    CharacterService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.generators.scene import SceneGenerator
from src.core.novels.services.generation.generators.scene_roadmap_validator import (
    SceneRoadmapVerdict,
)
from tests.fakes.outbound.ai.generator import FakeGenerator
from tests.fakes.outbound.database.repositories.character_repository import (
    FakeCharacterRepository,
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


class _AlwaysMatchValidator:
    async def validate(self, roadmap, scene, story_context=None):
        return SceneRoadmapVerdict(True, True, True, "")


class _AlwaysFailValidator:
    async def validate(self, roadmap, scene, story_context=None):
        return SceneRoadmapVerdict(False, False, False, "расхождение")


class _SequenceValidator:
    """Отдаёт результаты/ошибки по очереди; используется для проверки ретраев."""

    def __init__(self, results: list):
        self._results = list(results)

    async def validate(self, roadmap, scene, story_context=None):
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _character(character_id: int, name: str, is_protagonist: bool = False) -> Character:
    return Character(
        id=character_id,
        created_at=None,
        updated_at=None,
        novel_id=1,
        name=name,
        role="роль",
        arc="арка",
        voice_notes="голос",
        is_protagonist=is_protagonist,
    )


async def _build_sut(
    generator: FakeGenerator,
    characters: list[Character],
    scenes_count: int = 1,
    *,
    validator=None,
    max_validation_retries: int = 1,
    location_slug: str | None = None,
    time_of_day: str | None = None,
    day: int | None = None,
) -> tuple[SceneGenerator, Roadmap, FakeSceneRepository]:
    novel_repo = FakeNovelRepository()
    char_repo = FakeCharacterRepository()
    roadmap_repo = FakeRoadmapRepository()
    scene_repo = FakeSceneRepository(roadmap_repo)

    novel = await novel_repo.add(
        Novel(
            id=None,
            created_at=None,
            updated_at=None,
            title="Тень",
            public_description="",
            description="D",
            tone="tone",
        )
    )
    for character in characters:
        await char_repo.add(character)
    roadmap = await roadmap_repo.add(
        Roadmap(
            id=None,
            created_at=None,
            updated_at=None,
            novel_id=novel.id,
            step_id=1,
            title="Шаг 1",
            event="Событие шага",
            conflict="Конфликт шага",
            change="Изменение шага",
            target_choice=False,
            choice_stakes=None,
            scenes_count=scenes_count,
            location_slug=location_slug,
            time_of_day=time_of_day,
            day=day,
        )
    )
    sut = SceneGenerator(
        NovelService(novel_repo),
        RoadmapService(roadmap_repo),
        SceneService(scene_repo),
        CharacterService(char_repo),
        generator,
        validator or _AlwaysMatchValidator(),
        max_validation_retries=max_validation_retries,
    )
    return sut, roadmap, scene_repo


class TestSceneCast:
    async def test_resolves_names_and_forces_protagonist(self):
        """Протагонист добавляется в список участников, даже если LLM его не вернул."""
        generator = FakeGenerator().always_returns(
            {"title": "t", "description": "d", "characters": ["Виола"]}
        )
        cast = [_character(1, "Семён", is_protagonist=True), _character(2, "Виола")]
        sut, roadmap, _ = await _build_sut(generator, cast)

        scene = await sut.generate(roadmap.id)

        assert sorted(scene.character_ids) == [1, 2]

    async def test_empty_characters_still_has_protagonist(self):
        """Пустой список участников — сольная сцена протагониста."""
        generator = FakeGenerator().always_returns(
            {"title": "t", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True), _character(2, "Виола")]
        sut, roadmap, _ = await _build_sut(generator, cast)

        scene = await sut.generate(roadmap.id)

        assert scene.character_ids == [1]

    async def test_unknown_character_raises(self):
        """Неизвестное имя — ошибка генерации, а не молчаливый пропуск."""
        generator = FakeGenerator().always_returns(
            {"title": "t", "description": "d", "characters": ["Незнакомец"]}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(generator, cast)

        with pytest.raises(GenerationError):
            await sut.generate(roadmap.id)

    async def test_prompt_requests_characters(self):
        """Промпт сцены требует список участников, а не весь каст."""
        generator = FakeGenerator().always_returns(
            {"title": "t", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(generator, cast)

        await sut.generate(roadmap.id)

        assert '"characters"' in generator.last_system_prompt


class _RaisingValidator:
    def __init__(self, error: Exception | None = None):
        self._error = error or GenerationError("validator LLM failed")

    async def validate(self, roadmap, scene, story_context=None):
        raise self._error


class TestSceneValidationRetry:
    async def test_validator_transient_error_marks_needs_review(self):
        """Транзиентный сбой валидатора не валит джоб, а помечает сцену needs_review."""
        generator = FakeGenerator().always_returns(
            {"title": "t", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(
            generator, cast, validator=_RaisingValidator(), max_validation_retries=1
        )

        scene = await sut.generate(roadmap.id)

        assert scene.needs_review is True
        assert scene.review_reason is not None

    async def test_needs_review_scene_is_not_final(self):
        """Сцена с needs_review не закрывает шаг: флаги финала сбрасываются."""
        generator = FakeGenerator().always_returns(
            {"title": "t", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(
            generator, cast, validator=_AlwaysFailValidator(), max_validation_retries=0
        )

        scene = await sut.generate(roadmap.id)

        assert scene.needs_review is True
        assert scene.is_final_for_roadmap is False
        assert scene.is_final_for_novel is False

    async def test_validator_error_then_success_retries(self):
        """Один сбой валидатора → ретрай → успешная сцена без needs_review."""
        generator = FakeGenerator().always_returns(
            {"title": "t", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        validator = _SequenceValidator(
            [GenerationError("validator LLM failed"), SceneRoadmapVerdict(True, True, True, "")]
        )
        sut, roadmap, _ = await _build_sut(
            generator, cast, validator=validator, max_validation_retries=1
        )

        scene = await sut.generate(roadmap.id)

        assert scene.needs_review is False

    async def test_cast_error_then_success_retries(self):
        """Неизвестное имя → ретрай сценария → успешная сцена."""
        generator = FakeGenerator().returns(
            {"title": "t", "description": "d", "characters": ["Незнакомец"]}
        ).returns({"title": "t", "description": "d", "characters": []})
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(generator, cast, max_validation_retries=1)

        scene = await sut.generate(roadmap.id)

        assert scene.needs_review is False
        assert scene.character_ids == [1]


class TestScenePlaceTime:
    async def test_scene_inherits_step_place_time(self):
        """LLM не вернул место/время — сцена наследует их от шага роадмапа."""
        generator = FakeGenerator().always_returns(
            {"title": "t", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(
            generator, cast, location_slug="aidpost", time_of_day="day", day=3
        )

        scene = await sut.generate(roadmap.id)

        assert scene.location_slug == "aidpost"
        assert scene.time_of_day == "day"
        assert scene.day == 3

    async def test_scene_explicit_place_time_wins(self):
        """Явно заданные LLM место/время сохраняются, а не затираются шагом."""
        generator = FakeGenerator().always_returns(
            {
                "title": "t",
                "description": "d",
                "characters": [],
                "location_slug": "beach",
                "time_of_day": "night",
                "day": 4,
            }
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(
            generator, cast, location_slug="aidpost", time_of_day="day", day=3
        )

        scene = await sut.generate(roadmap.id)

        assert scene.location_slug == "beach"
        assert scene.time_of_day == "night"
        assert scene.day == 4

    async def test_prompt_declares_step_place_time(self):
        generator = FakeGenerator().always_returns(
            {"title": "t", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(
            generator, cast, location_slug="aidpost", time_of_day="day", day=3
        )

        await sut.generate(roadmap.id)

        user_prompt = generator.last_user_prompt
        assert "Step place and time" in user_prompt
        assert "aidpost" in user_prompt
        assert "day 3" in user_prompt


def _previous_scene(title: str, character_ids: list[int]) -> Scene:
    return Scene(
        id=9,
        created_at=None,
        updated_at=None,
        roadmap_id=1,
        title=title,
        description="d",
        order=1,
        character_ids=character_ids,
    )


class TestSceneDuplicate:
    async def test_duplicate_retries_into_new_scene(self):
        """Повтор предыдущей сцены → ретрай → принимается другая сцена."""
        generator = FakeGenerator().returns(
            {"title": "Проверка зрения", "description": "d", "characters": []}
        ).returns(
            {"title": "После проверки", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(generator, cast, max_validation_retries=1)
        previous = _previous_scene("Проверка зрения", [1])

        scene = await sut.generate(roadmap.id, previous_scenes=[previous])

        assert scene.needs_review is False
        assert scene.title == "После проверки"

    async def test_duplicate_exhausts_retries_marks_needs_review(self):
        """Повтор при исчерпанных ретраях помечается needs_review."""
        generator = FakeGenerator().always_returns(
            {"title": "Проверка зрения", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(
            generator, cast, max_validation_retries=0
        )
        previous = _previous_scene("Проверка зрения", [1])

        scene = await sut.generate(roadmap.id, previous_scenes=[previous])

        assert scene.needs_review is True
        assert "повторяет" in (scene.review_reason or "")

    async def test_same_place_but_new_title_is_not_duplicate(self):
        """То же место/день/участники, но другое название — не повтор."""
        generator = FakeGenerator().always_returns(
            {"title": "Новый разговор", "description": "d", "characters": []}
        )
        cast = [_character(1, "Семён", is_protagonist=True)]
        sut, roadmap, _ = await _build_sut(generator, cast, location_slug="aidpost", day=1)
        previous = _previous_scene("Старый разговор", [1])
        previous.location_slug = "aidpost"
        previous.day = 1

        scene = await sut.generate(roadmap.id, previous_scenes=[previous])

        assert scene.needs_review is False
        assert scene.title == "Новый разговор"
