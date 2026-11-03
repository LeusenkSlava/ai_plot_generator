"""Проводка design-прохода в саге генерации: какой вариант его получает."""

from src.core.novels.models import (
    Novel,
    PlotDesign,
    PlotThread,
    PromptVariant,
    Roadmap,
    Scene,
)
from src.core.novels.services.generation.composition import NovelCompositionService
from src.core.novels.services.generation.transactions import noop_step


class _StubNovelGenerator:
    def __init__(self, prompt_variant: PromptVariant) -> None:
        self._prompt_variant = prompt_variant

    async def generate(self, user_prompt: str, **kwargs) -> Novel:
        return Novel(
            id=1,
            created_at=None,
            updated_at=None,
            title="Совёнок",
            public_description="",
            description="D",
            tone="t",
            prompt_variant=self._prompt_variant,
        )


class _StubCharacterGenerator:
    async def generate(self, novel_id: int, *, step) -> list:
        return []


class _RecordingDesignGenerator:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def generate(self, novel_id: int, *, user_prompt: str, step) -> PlotDesign:
        self.calls.append(novel_id)
        return PlotDesign(
            shape="relationship_arc",
            genres=["romcom"],
            through_line="Принять себя",
            threads=[PlotThread("нить", ["Совёнок"], 2, 4)],
            tropes=[],
            pivot="Поворот",
            tone_curve=["comedy"],
        )


class _RecordingRoadmapGenerator:
    def __init__(self) -> None:
        self.designs: list[PlotDesign | None] = []

    async def generate(self, novel_id: int, *, user_prompt: str, design, step):
        self.designs.append(design)
        return [
            Roadmap(
                id=10,
                created_at=None,
                updated_at=None,
                novel_id=novel_id,
                depth=1,
                title="Шаг",
                event="Событие",
                conflict="",
                change="Изменение",
                target_choice=False,
                choice_stakes=None,
                scenes_count=1,
            )
        ]


class _StubSceneGenerator:
    async def generate(self, roadmap_id: int, *, step) -> Scene:
        # needs_review=True обрывает сагу сразу после первой сцены.
        return Scene(
            id=20,
            created_at=None,
            updated_at=None,
            roadmap_id=roadmap_id,
            title="Сцена",
            description="d",
            order=1,
            needs_review=True,
        )


class _Unused:
    async def generate(self, *args, **kwargs):  # pragma: no cover - не вызывается
        raise AssertionError("generator must not be called")


async def _create(variant: PromptVariant):
    design_generator = _RecordingDesignGenerator()
    roadmap_generator = _RecordingRoadmapGenerator()
    composition = NovelCompositionService(
        novel_generator=_StubNovelGenerator(variant),
        character_generator=_StubCharacterGenerator(),
        plot_design_generator=design_generator,
        roadmap_generator=roadmap_generator,
        scene_generator=_StubSceneGenerator(),
        dialogue_generator=_Unused(),
        story_context_generator=_Unused(),
    )

    await composition.create("p", prompt_variant=variant, step=noop_step)
    return design_generator.calls, roadmap_generator.designs


class TestPlotDesignWiring:
    async def test_nsfw_high_runs_design_pass(self):
        design_calls, designs = await _create(PromptVariant.NSFW_HIGH)

        assert design_calls == [1]
        assert len(designs) == 1
        assert designs[0] is not None
        assert designs[0].shape == "relationship_arc"

    async def test_nsfw_extra_skips_design_pass(self):
        design_calls, designs = await _create(PromptVariant.NSFW_EXTRA)

        assert design_calls == []
        assert designs == [None]

    async def test_other_variants_run_design_pass(self):
        for variant in (
            PromptVariant.DEFAULT,
            PromptVariant.NSFW_LOW,
            PromptVariant.NSFW_MEDIUM,
        ):
            design_calls, designs = await _create(variant)

            assert design_calls == [1], variant
            assert designs[0] is not None, variant
            assert designs[0].shape == "relationship_arc", variant
