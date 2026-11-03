"""Сцена записана в ``scenes``, но реплик нет (воркер упал между сценой и диалогом).

Повторная задача должна дописать диалог, а не вернуть сцену как готовую.
"""

import dataclasses

import pytest

from src.core.novels.exceptions import SceneOrderError
from src.core.novels.models import DialogueLine, LineKind, Novel, Roadmap, Scene
from src.core.novels.services.generation.continuation import SceneContinuationService
from src.core.novels.services.generation.transactions import noop_step

NOVEL_ID = 7


class _NovelRepo:
    def __init__(self, novel: Novel):
        self.novel = novel

    async def get_by_id(self, novel_id: int):
        return self.novel if novel_id == self.novel.id else None


class _RoadmapRepo:
    def __init__(self, items):
        self.items = list(items)

    async def list_by_novel_id(self, novel_id: int):
        return [r for r in self.items if r.novel_id == novel_id]


class _SceneRepo:
    def __init__(self, items):
        self.items = list(items)

    async def list_by_novel_id(self, novel_id: int):
        return list(self.items)

    async def get_by_id(self, scene_id: int):
        return next((s for s in self.items if s.id == scene_id), None)

    async def delete(self, scene_id: int):
        self.items = [s for s in self.items if s.id != scene_id]


class _LineRepo:
    def __init__(self, items=()):
        self.items = list(items)

    async def list_by_novel_id(self, novel_id: int):
        return list(self.items)


class _EmptyRepo:
    async def list_by_novel_id(self, novel_id: int):
        return []


class _SceneGeneratorStub:
    def __init__(self, scene: Scene | None = None):
        self.scene = scene
        self.calls = 0

    async def generate(self, roadmap_id, **kwargs):
        self.calls += 1
        if self.scene is None:
            raise AssertionError("сцена не должна генерироваться заново")
        return dataclasses.replace(self.scene, roadmap_id=roadmap_id)


class _DialogueGeneratorStub:
    def __init__(self):
        self.calls = []

    async def generate(self, scene_id, **kwargs):
        self.calls.append({"scene_id": scene_id, **kwargs})
        return []


class _StoryContextGeneratorStub:
    def __init__(self):
        self.calls = []

    async def generate(self, scene_id, **kwargs):
        self.calls.append({"scene_id": scene_id, **kwargs})
        return "контекст"


def _novel() -> Novel:
    return Novel(
        id=NOVEL_ID,
        created_at=None,
        updated_at=None,
        title="История",
        public_description="",
        description="",
        tone="",
    )


def _roadmap(roadmap_id=10, *, scenes_count=1) -> Roadmap:
    return Roadmap(
        id=roadmap_id,
        created_at=None,
        updated_at=None,
        novel_id=NOVEL_ID,
        depth=1,
        title="шаг 1",
        event="",
        conflict="",
        change="",
        target_choice=False,
        choice_stakes=None,
        scenes_count=scenes_count,
        parent_roadmap_id=None,
        branch_id=0,
    )


def _scene(
    scene_id=100,
    *,
    roadmap_id=10,
    order=1,
    final_for_novel=False,
    story_context=None,
) -> Scene:
    return Scene(
        id=scene_id,
        created_at=None,
        updated_at=None,
        roadmap_id=roadmap_id,
        title="сцена 1",
        description="",
        order=order,
        is_final_for_roadmap=True,
        is_final_for_novel=final_for_novel,
        story_context=story_context,
    )


def _line(line_id=1, *, scene_id=100, order=1) -> DialogueLine:
    return DialogueLine(
        id=line_id,
        created_at=None,
        updated_at=None,
        novel_id=NOVEL_ID,
        scene_id=scene_id,
        character_id=None,
        order=order,
        text="реплика",
        is_final_for_scene=True,
        kind=LineKind.NARRATION,
    )


def _service(
    *,
    scenes,
    lines,
    roadmaps=None,
    scene_generator=None,
    dialogue_generator=None,
):
    return SceneContinuationService(
        novel_repository=_NovelRepo(_novel()),
        roadmap_repository=_RoadmapRepo(roadmaps or [_roadmap()]),
        scene_repository=_SceneRepo(scenes),
        dialogue_line_repository=_LineRepo(lines),
        roadmap_choice_repository=_EmptyRepo(),
        player_choice_repository=_EmptyRepo(),
        scene_generator=scene_generator or _SceneGeneratorStub(),
        dialogue_generator=dialogue_generator or _DialogueGeneratorStub(),
        story_context_generator=_StoryContextGeneratorStub(),
    )


class TestSceneWithoutDialogueIsCompleted:
    async def test_existing_scene_without_lines_gets_dialogue(self):
        orphan = _scene(100)
        dialogue = _DialogueGeneratorStub()
        service = _service(
            scenes=[orphan], lines=[], dialogue_generator=dialogue
        )

        scene = await service.generate(NOVEL_ID, 10, 1, step=noop_step)

        assert scene.id == 100
        assert [c["scene_id"] for c in dialogue.calls] == [100]

    async def test_orphan_scene_is_not_previous_scene_for_its_own_prompt(self):
        """Предыдущая сцена для промпта — из прошлого шага, а не сама сцена-сирота."""
        first_step = _roadmap(10)
        second_step = dataclasses.replace(_roadmap(20), depth=2, parent_roadmap_id=10)
        previous = _scene(90, roadmap_id=10)
        orphan = _scene(100, roadmap_id=20, order=2)
        dialogue = _DialogueGeneratorStub()
        service = _service(
            roadmaps=[first_step, second_step],
            scenes=[previous, orphan],
            lines=[],
            dialogue_generator=dialogue,
        )

        await service.generate(NOVEL_ID, 20, 1, step=noop_step)

        assert dialogue.calls[0]["scene_id"] == 100
        assert dialogue.calls[0]["previous_scene"] is previous

    async def test_existing_scene_with_lines_is_idempotent(self):
        """Повторная доставка готовой сцены не перегенерирует диалог."""
        scene = _scene(100)
        dialogue = _DialogueGeneratorStub()
        scene_generator = _SceneGeneratorStub()
        service = _service(
            scenes=[scene],
            lines=[_line(1, scene_id=100)],
            scene_generator=scene_generator,
            dialogue_generator=dialogue,
        )

        result = await service.generate(NOVEL_ID, 10, 1, step=noop_step)

        assert result.id == 100
        assert dialogue.calls == []
        assert scene_generator.calls == 0

    async def test_normal_path_still_generates_scene_then_dialogue(self):
        created = _scene(100)
        scene_generator = _SceneGeneratorStub(created)
        dialogue = _DialogueGeneratorStub()
        service = _service(
            scenes=[],
            lines=[],
            scene_generator=scene_generator,
            dialogue_generator=dialogue,
        )

        result = await service.generate(NOVEL_ID, 10, 1, step=noop_step)

        assert result.id == 100
        assert scene_generator.calls == 1
        assert [c["scene_id"] for c in dialogue.calls] == [100]

    async def test_orphan_context_ignores_scenes_from_the_future(self):
        """Сирота не последняя: контекст берётся только из order < scene.order."""
        first_step = _roadmap(10)
        second_step = dataclasses.replace(_roadmap(20), depth=2, parent_roadmap_id=10)
        third_step = dataclasses.replace(_roadmap(30), depth=3, parent_roadmap_id=20)
        previous = _scene(90, roadmap_id=10, order=1, story_context="прошлое")
        orphan = _scene(100, roadmap_id=20, order=2, story_context="своё")
        future = _scene(110, roadmap_id=30, order=3, story_context="будущее")
        dialogue = _DialogueGeneratorStub()
        service = _service(
            roadmaps=[first_step, second_step, third_step],
            scenes=[previous, orphan, future],
            lines=[_line(1, scene_id=90), _line(2, scene_id=110)],
            dialogue_generator=dialogue,
        )

        await service.generate(NOVEL_ID, 20, 1, step=noop_step)

        call = dialogue.calls[0]
        assert call["previous_scene"] is previous
        assert "прошлое" in call["story_context"]
        assert "будущее" not in call["story_context"]
        assert [line.scene_id for line in call["previous_lines"]] == [90]
        assert [line.scene_id for line in call["all_lines"]] == [90]


class TestEarlierOrphanBlocksNextStep:
    async def test_next_step_is_not_generated_over_scene_without_dialogue(self):
        """Шаг закрыт по числу сцен, но предыдущая сцена без реплик → не вперёд."""
        first_step = _roadmap(10)
        second_step = dataclasses.replace(_roadmap(20), depth=2, parent_roadmap_id=10)
        orphan = _scene(100, roadmap_id=10, order=1)
        scene_generator = _SceneGeneratorStub()
        service = _service(
            roadmaps=[first_step, second_step],
            scenes=[orphan],
            lines=[],
            scene_generator=scene_generator,
        )

        with pytest.raises(SceneOrderError):
            await service.generate(NOVEL_ID, 20, 1, step=noop_step)

        assert scene_generator.calls == 0

