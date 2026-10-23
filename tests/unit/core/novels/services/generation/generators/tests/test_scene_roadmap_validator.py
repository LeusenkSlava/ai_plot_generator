from src.core.novels.models import Roadmap, Scene
from src.core.novels.services.generation.generators.scene_roadmap_validator import (
    SceneRoadmapValidator,
)
from tests.fakes.outbound.ai.generator import FakeGenerator


def _roadmap(**fields) -> Roadmap:
    return Roadmap(
        id=1,
        created_at=None,
        updated_at=None,
        novel_id=1,
        step_id=1,
        title="Шаг",
        goal="Цель",
        target_choice=False,
        choice_stakes=None,
        scenes_count=2,
        **fields,
    )


def _scene(**fields) -> Scene:
    return Scene(
        id=1,
        created_at=None,
        updated_at=None,
        roadmap_id=1,
        title="Сцена",
        description="d",
        order=1,
        **fields,
    )


class TestDeterministicShortCircuit:
    async def test_location_mismatch_rejected_without_llm(self):
        generator = FakeGenerator()
        validator = SceneRoadmapValidator(generator)
        roadmap = _roadmap(location_slug="aidpost")
        scene = _scene(location_slug="beach")

        verdict = await validator.validate(roadmap, scene)

        assert verdict.location_match is False
        assert verdict.matches is False
        assert "beach" in verdict.reason
        assert generator.not_called

    async def test_day_mismatch_rejected_without_llm(self):
        generator = FakeGenerator()
        validator = SceneRoadmapValidator(generator)
        roadmap = _roadmap(day=1)
        scene = _scene(day=2)

        verdict = await validator.validate(roadmap, scene)

        assert verdict.time_match is False
        assert verdict.matches is False
        assert generator.not_called

    async def test_match_uses_llm(self):
        generator = FakeGenerator().always_returns(
            {"theme_match": True, "location_match": True, "time_match": True, "reason": ""}
        )
        validator = SceneRoadmapValidator(generator)
        roadmap = _roadmap(location_slug="aidpost", day=1)
        scene = _scene(location_slug="aidpost", day=1)

        verdict = await validator.validate(roadmap, scene)

        assert verdict.matches is True
        assert generator.called

    async def test_no_step_place_skips_short_circuit(self):
        """Шаг без места/дня (старые данные) не триггерит короткое замыкание."""
        generator = FakeGenerator().always_returns(
            {"theme_match": True, "location_match": True, "time_match": True, "reason": ""}
        )
        validator = SceneRoadmapValidator(generator)
        roadmap = _roadmap()
        scene = _scene(location_slug="beach", day=2)

        verdict = await validator.validate(roadmap, scene)

        assert verdict.matches is True
        assert generator.called


class TestPromptIncludesPlaceTime:
    async def test_prompt_contains_place_and_time_fields(self):
        generator = FakeGenerator().always_returns(
            {"theme_match": True, "location_match": True, "time_match": True, "reason": ""}
        )
        validator = SceneRoadmapValidator(generator)
        roadmap = _roadmap(location_slug="aidpost", time_of_day="day", day=3)
        scene = _scene(location_slug="aidpost", time_of_day="day", day=3)

        await validator.validate(roadmap, scene)

        user_prompt = generator.last_user_prompt
        assert "Step location: aidpost" in user_prompt
        assert "Step time of day: day" in user_prompt
        assert "Step day: 3" in user_prompt
        assert "Scene location: aidpost" in user_prompt
        assert "Scene day: 3" in user_prompt
