import pytest

from src.core.codex.models import BackgroundTags, Tag, TagType
from src.core.novels.exceptions import GenerationError
from src.core.novels.models import Character, Novel
from src.core.novels.services.crud import (
    CharacterService,
    NovelService,
    RoadmapService,
)
from src.core.novels.services.generation.generators.roadmap import RoadmapGenerator
from tests.fakes.outbound.ai.generator import FakeGenerator
from tests.fakes.outbound.codex.client import FakeCodexService
from tests.fakes.outbound.database.repositories.character_repository import (
    FakeCharacterRepository,
)
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)
from tests.fakes.outbound.database.repositories.roadmap_repository import (
    FakeRoadmapRepository,
)


def _location(slug: str, name: str) -> Tag:
    return Tag(id=0, type=TagType.LOCATION, slug=slug, name=name)


def _time(slug: str, name: str) -> Tag:
    return Tag(id=0, type=TagType.TIME_OF_DAY, slug=slug, name=name)


def _tags() -> BackgroundTags:
    return BackgroundTags(
        base=[_location("aidpost", "Медпункт"), _location("beach", "Пляж")],
        modifiers=[_time("morning", "Утро"), _time("day", "День"), _time("night", "Ночь")],
    )


async def _build_sut(
    generator: FakeGenerator, codex: FakeCodexService, *, universe_id: int | None = 1
) -> tuple[RoadmapGenerator, Novel]:
    novel_repo = FakeNovelRepository()
    char_repo = FakeCharacterRepository()
    roadmap_repo = FakeRoadmapRepository()

    novel = await novel_repo.add(
        Novel(
            id=None,
            created_at=None,
            updated_at=None,
            title="Тень",
            public_description="",
            description="D",
            tone="tone",
            universe_id=universe_id,
        )
    )
    await char_repo.add(
        Character(
            id=None,
            created_at=None,
            updated_at=None,
            novel_id=novel.id,
            name="Семён",
            role="роль",
            arc="арка",
            voice_notes="голос",
            is_protagonist=True,
        )
    )
    sut = RoadmapGenerator(
        NovelService(novel_repo),
        RoadmapService(roadmap_repo),
        CharacterService(char_repo),
        codex,
        generator,
    )
    return sut, novel


def _step(*, location="aidpost", time="day", day=1, **extra) -> dict:
    step = {
        "title": "Шаг",
        "goal": "Цель",
        "scenes_count": 2,
        "location_slug": location,
        "time_of_day": time,
        "day": day,
    }
    step.update(extra)
    return step


class TestRoadmapPlaceTime:
    async def test_catalog_in_prompt(self):
        codex = FakeCodexService()
        codex.add_background_tags(1, _tags())
        generator = FakeGenerator().always_returns({"roadmap": [_step()]})
        sut, novel = await _build_sut(generator, codex)

        await sut.generate(novel.id)

        user_prompt = generator.last_user_prompt
        assert "aidpost=Медпункт" in user_prompt
        assert "beach=Пляж" in user_prompt
        assert "morning=Утро" in user_prompt
        generator.assert_system_contains("location_slug", "time_of_day", "day")

    async def test_system_prompt_constrains_goal_to_cast(self):
        """goal не должен упоминать персонажей вне каста — иначе сцены падают на проверке."""
        codex = FakeCodexService()
        codex.add_background_tags(1, _tags())
        generator = FakeGenerator().always_returns({"roadmap": [_step()]})
        sut, novel = await _build_sut(generator, codex)

        await sut.generate(novel.id)

        generator.assert_system_contains(
            "только на персонажах из списка",
            "не упоминай в goal персонажей",
        )

    async def test_system_prompt_guides_structure(self):
        """Роадмап должен вести сквозную линию, давать ставки и арки персонажей.

        Структура задаётся кругом Хармана (8 битов).
        """
        codex = FakeCodexService()
        codex.add_background_tags(1, _tags())
        generator = FakeGenerator().always_returns({"roadmap": [_step()]})
        sut, novel = await _build_sut(generator, codex)

        await sut.generate(novel.id)

        generator.assert_system_contains(
            "от 8 до 12",
            "круг Хармана",
            "8 битов",
            "сквозная линия",
            "поворот",
            "мини-арку",
            "препятствие",
        )

    async def test_parses_place_time_day(self):
        codex = FakeCodexService()
        codex.add_background_tags(1, _tags())
        generator = FakeGenerator().always_returns(
            {"roadmap": [_step(location="beach", time="night", day=2)]}
        )
        sut, novel = await _build_sut(generator, codex)

        result = await sut.generate(novel.id)

        assert len(result) == 1
        assert result[0].location_slug == "beach"
        assert result[0].time_of_day == "night"
        assert result[0].day == 2

    async def test_day_does_not_decrease(self):
        """Откат дня у следующего шага наследует предыдущий день."""
        codex = FakeCodexService()
        codex.add_background_tags(1, _tags())
        generator = FakeGenerator().always_returns(
            {"roadmap": [_step(day=3), _step(day=1)]}
        )
        sut, novel = await _build_sut(generator, codex)

        result = await sut.generate(novel.id)

        assert [r.day for r in result] == [3, 3]

    async def test_day_inherited_when_missing(self):
        codex = FakeCodexService()
        codex.add_background_tags(1, _tags())
        generator = FakeGenerator().always_returns(
            {"roadmap": [_step(day=2), _step(day=None)]}
        )
        sut, novel = await _build_sut(generator, codex)

        result = await sut.generate(novel.id)

        assert [r.day for r in result] == [2, 2]

    async def test_blank_slug_is_none(self):
        codex = FakeCodexService()
        codex.add_background_tags(1, _tags())
        generator = FakeGenerator().always_returns(
            {"roadmap": [_step(location="", time="", day=None)]}
        )
        sut, novel = await _build_sut(generator, codex)

        result = await sut.generate(novel.id)

        assert result[0].location_slug is None
        assert result[0].time_of_day is None
        assert result[0].day is None


class TestRoadmapWithoutUniverse:
    async def test_codex_not_called_and_fields_none(self):
        codex = FakeCodexService()
        generator = FakeGenerator().always_returns({"roadmap": [_step()]})
        sut, novel = await _build_sut(generator, codex, universe_id=None)

        result = await sut.generate(novel.id)

        assert codex.calls == []
        assert result[0].location_slug is None
        assert result[0].time_of_day is None
        assert result[0].day == 1

    async def test_codex_failure_wrapped(self):
        codex = FakeCodexService()
        codex.fail_on("get_background_tags")
        generator = FakeGenerator().always_returns({"roadmap": [_step()]})
        sut, novel = await _build_sut(generator, codex)

        with pytest.raises(GenerationError, match="background tags"):
            await sut.generate(novel.id)
