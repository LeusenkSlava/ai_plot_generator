from dataclasses import asdict

import pytest

from src.core.novels.exceptions import GenerationError, PromptNotFoundError
from src.core.novels.models import (
    Novel,
    PlotDesign,
    PlotThread,
    PromptKey,
    PromptVariant,
)
from src.core.novels.services.crud import (
    CharacterService,
    NovelService,
    RoadmapService,
)
from src.core.novels.services.generation.generators.plot_design import (
    PlotDesignGenerator,
)
from src.core.novels.services.generation.generators.roadmap import RoadmapGenerator
from src.core.novels.services.generation.prompts.catalog import PromptCatalog
from tests.factories import novel_character_domain, novel_domain
from tests.fakes.outbound.ai.generator import FakeGenerator
from tests.fakes.outbound.codex.client import FakeCodexService
from tests.fakes.outbound.database.repositories.character_repository import (
    FakeCharacterRepository,
)
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)
from tests.fakes.outbound.database.repositories.prompt_repository import (
    FakePromptRepository,
)
from tests.fakes.outbound.database.repositories.roadmap_repository import (
    FakeRoadmapRepository,
)

_PLOT_DESIGN_SYSTEM = (
    "You are a story designer. Answer STRICTLY as JSON.\n"
    "Choose the shape from the catalog:\n{shape_catalog}\n{russian_note}"
)
_PLOT_DESIGN_USER = (
    "Title: {title}\nDescription: {description}\nNarrative tone: {tone}"
    "{characters_block}\nUser request: {user_prompt}"
)

_ROADMAP_SYSTEM = (
    "You are an author. Answer STRICTLY as JSON.\n{schema}"
    "{choice_instructions}{russian_note}"
)
_ROADMAP_USER = (
    "User request: {user_prompt}\n\nTitle: {title}\nDescription: {description}"
    "\nNarrative tone: {tone}\n\nStory shape:\n{shape_block}\n\n"
    "Design brief:\n{design_block}{place_time_catalog}{characters_block}"
)


def _design_payload(**overrides) -> dict:
    payload = {
        "shape": "relationship_arc",
        "genres": ["romcom", "erotica"],
        "through_line": "Герой учится принимать себя",
        "threads": [
            {
                "name": "размер/секрет",
                "characters": ["Совёнок", "Алиса"],
                "min_steps": 2,
                "max_steps": 4,
            }
        ],
        "tropes": ["secret_reveal"],
        "pivot": "Секрет выходит наружу",
        "tone_curve": ["comedy", "drama"],
    }
    payload.update(overrides)
    return payload


def _roadmap_step(**extra) -> dict:
    step = {
        "title": "Шаг",
        "event": "Событие",
        "conflict": "Конфликт",
        "change": "Изменение",
        "scenes_count": 2,
        "location_slug": "",
        "time_of_day": "",
        "day": 1,
    }
    step.update(extra)
    return step


async def _seed_novel(repo: FakeNovelRepository, characters: list[dict]):
    char_repo = FakeCharacterRepository()
    novel = await repo.add(novel_domain(prompt_variant=PromptVariant.NSFW_HIGH))
    for fields in characters:
        await char_repo.add(novel_character_domain(novel_id=novel.id, **fields))
    return novel, char_repo


def _catalog(prompts: FakePromptRepository) -> PromptCatalog:
    return PromptCatalog(prompts)


def _seed_plot_design_prompt(prompts: FakePromptRepository) -> None:
    prompts.set_active(
        PromptKey.PLOT_DESIGN,
        PromptVariant.NSFW_HIGH,
        system_template=_PLOT_DESIGN_SYSTEM,
        user_template=_PLOT_DESIGN_USER,
    )


def _seed_roadmap_prompt(prompts: FakePromptRepository) -> None:
    prompts.set_active(
        PromptKey.ROADMAP,
        PromptVariant.NSFW_HIGH,
        system_template=_ROADMAP_SYSTEM,
        user_template=_ROADMAP_USER,
    )


async def _build_sut(
    generator: FakeGenerator,
) -> tuple[PlotDesignGenerator, NovelService, FakeNovelRepository]:
    novel_repo = FakeNovelRepository()
    _novel, char_repo = await _seed_novel(
        novel_repo,
        [
            {"name": "Совёнок", "is_protagonist": True, "arc": "Принять себя"},
            {"name": "Алиса", "role": "подруга"},
        ],
    )
    prompts = FakePromptRepository()
    _seed_plot_design_prompt(prompts)

    sut = PlotDesignGenerator(
        NovelService(novel_repo),
        CharacterService(char_repo),
        generator,
        prompt_catalog=_catalog(prompts),
    )
    return sut, NovelService(novel_repo), novel_repo


class TestPlotDesignPrompt:
    async def test_prompt_contains_shape_catalog_and_cast(self):
        generator = FakeGenerator().always_returns(_design_payload())
        sut, novel_service, _repo = await _build_sut(generator)
        novel = await novel_service.get(1)

        await sut.generate(novel.id, user_prompt="история про размер")

        generator.assert_system_contains("- hero_cycle:", "- relationship_arc:")
        user_prompt = generator.last_user_prompt
        assert "Title: Тень над лесом" in user_prompt
        assert "Narrative tone:" in user_prompt
        assert "- Алиса" in user_prompt
        assert "Protagonist: Совёнок" in user_prompt
        assert "User request: история про размер" in user_prompt

    async def test_single_cheap_call(self):
        generator = FakeGenerator().always_returns(_design_payload())
        sut, novel_service, _repo = await _build_sut(generator)
        novel = await novel_service.get(1)

        await sut.generate(novel.id, user_prompt="p")

        assert generator.call_count == 1
        assert generator.think_flags == [False]
        assert generator.efforts == [None]


class TestPlotDesignResult:
    async def test_returns_parsed_design(self):
        generator = FakeGenerator().always_returns(_design_payload())
        sut, novel_service, _repo = await _build_sut(generator)
        novel = await novel_service.get(1)

        design = await sut.generate(novel.id, user_prompt="p")

        assert design == PlotDesign(
            shape="relationship_arc",
            genres=["romcom", "erotica"],
            through_line="Герой учится принимать себя",
            threads=[PlotThread("размер/секрет", ["Совёнок", "Алиса"], 2, 4)],
            tropes=["secret_reveal"],
            pivot="Секрет выходит наружу",
            tone_curve=["comedy", "drama"],
        )

    async def test_snapshot_saved_on_novel(self):
        generator = FakeGenerator().always_returns(_design_payload())
        sut, novel_service, novel_repo = await _build_sut(generator)
        novel = await novel_service.get(1)

        design = await sut.generate(novel.id, user_prompt="p")

        stored = await novel_repo.get_by_id(novel.id)
        assert stored.plot_design == asdict(design)


class TestPlotDesignRetryAndErrors:
    async def test_invalid_response_retried_once(self):
        generator = FakeGenerator().returns({"threads": []}).returns(_design_payload())
        sut, novel_service, _repo = await _build_sut(generator)
        novel = await novel_service.get(1)

        design = await sut.generate(novel.id, user_prompt="p")

        assert design.shape == "relationship_arc"
        assert generator.call_count == 2

    async def test_two_invalid_responses_raise(self):
        generator = FakeGenerator().always_returns({"threads": []})
        sut, novel_service, _repo = await _build_sut(generator)
        novel = await novel_service.get(1)

        with pytest.raises(GenerationError, match="no threads"):
            await sut.generate(novel.id, user_prompt="p")

        assert generator.call_count == 2

    async def test_llm_failure_is_not_retried(self):
        generator = FakeGenerator().raises(RuntimeError("LLM down"))
        sut, novel_service, novel_repo = await _build_sut(generator)
        novel = await novel_service.get(1)

        with pytest.raises(GenerationError):
            await sut.generate(novel.id, user_prompt="p")

        assert generator.call_count == 1
        assert (await novel_repo.get_by_id(novel.id)).plot_design is None

    async def test_unknown_novel_raises(self):
        generator = FakeGenerator().always_returns(_design_payload())
        sut, _service, _repo = await _build_sut(generator)

        with pytest.raises(GenerationError, match="not found"):
            await sut.generate(999, user_prompt="p")

        assert generator.not_called

    async def test_missing_template_raises(self):
        """Без активного шаблона plot_design (вариант не поддержан) — ошибка каталога."""
        generator = FakeGenerator().always_returns(_design_payload())
        novel_repo = FakeNovelRepository()
        _novel, char_repo = await _seed_novel(novel_repo, [{"name": "Алиса"}])
        sut = PlotDesignGenerator(
            NovelService(novel_repo),
            CharacterService(char_repo),
            generator,
            prompt_catalog=_catalog(FakePromptRepository()),
        )

        with pytest.raises(PromptNotFoundError):
            await sut.generate(1, user_prompt="p")

        assert generator.not_called


async def _build_roadmap_sut(
    generator: FakeGenerator,
) -> tuple[RoadmapGenerator, Novel]:
    novel_repo = FakeNovelRepository()
    novel, char_repo = await _seed_novel(
        novel_repo,
        [{"name": "Совёнок", "is_protagonist": True, "arc": "Принять себя"}],
    )
    prompts = FakePromptRepository()
    _seed_roadmap_prompt(prompts)

    sut = RoadmapGenerator(
        NovelService(novel_repo),
        RoadmapService(FakeRoadmapRepository()),
        CharacterService(char_repo),
        FakeCodexService(),
        generator,
        prompt_catalog=_catalog(prompts),
    )
    return sut, novel


class TestRoadmapWithDesign:
    @staticmethod
    def _design() -> PlotDesign:
        return PlotDesign(
            shape="relationship_arc",
            genres=["romcom"],
            through_line="Герой учится принимать себя",
            threads=[PlotThread("размер/секрет", ["Совёнок"], 2, 4)],
            tropes=["secret_reveal"],
            pivot="Секрет выходит наружу",
            tone_curve=["comedy", "drama"],
        )

    async def test_shape_and_budget_reach_prompt(self):
        generator = FakeGenerator().always_returns({"roadmap": [_roadmap_step()]})
        sut, novel = await _build_roadmap_sut(generator)

        await sut.generate(novel.id, user_prompt="p", design=self._design())

        user_prompt = generator.last_user_prompt
        assert "1. Encounter" in user_prompt
        assert "7. Commitment" in user_prompt
        assert "Chosen shape: relationship_arc" in user_prompt
        assert "- размер/секрет [2..4 steps] — characters: Совёнок" in user_prompt
        generator.assert_system_contains("beat_type")

    async def test_without_design_blocks_are_empty(self):
        generator = FakeGenerator().always_returns({"roadmap": [_roadmap_step()]})
        sut, novel = await _build_roadmap_sut(generator)

        await sut.generate(novel.id, user_prompt="p")

        user_prompt = generator.last_user_prompt
        assert "Chosen shape:" not in user_prompt
        assert "Encounter" not in user_prompt
        generator.assert_system_contains("beat_type")

    async def test_beat_type_parsed_and_blank_becomes_none(self):
        generator = FakeGenerator().always_returns(
            {
                "roadmap": [
                    _roadmap_step(beat_type="obstacle"),
                    _roadmap_step(beat_type="  "),
                    _roadmap_step(),
                ]
            }
        )
        sut, novel = await _build_roadmap_sut(generator)

        result = await sut.generate(novel.id, user_prompt="p", design=self._design())

        assert [step.beat_type for step in result] == ["obstacle", None, None]

