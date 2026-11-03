"""Хвост проигрывания, когда сцена записана, а реплик ещё нет.

Такой шаг отдаётся как ``need_generation``/``generating``, а не ``finished``.
"""

from src.core.novels.models import (
    DialogueLine,
    LineKind,
    Novel,
    Roadmap,
    RoadmapChoice,
    Scene,
)
from src.core.novels.services.playback import NovelPlaybackService, PlaybackStatus

NOVEL_ID = 7


# --- репозитории-заглушки ---------------------------------------------------


class _ByNovelRepo:
    """Общий репозиторий: элементы с id и novel_id."""

    def __init__(self, items=()):
        self.items = list(items)

    async def get_by_id(self, item_id: int):
        return next((i for i in self.items if i.id == item_id), None)

    async def list_by_novel_id(self, novel_id: int):
        return [i for i in self.items if i.novel_id == novel_id]


class _SceneRepo(_ByNovelRepo):
    """Сцены в порядке проигрывания (шаг -> сцена)."""

    def __init__(self, items=(), roadmaps=()):
        super().__init__(items)
        self._depth_by_roadmap = {r.id: r.depth for r in roadmaps}

    async def list_by_novel_id(self, novel_id: int):
        return sorted(
            (s for s in self.items if s.roadmap_id in self._depth_by_roadmap),
            key=lambda s: (self._depth_by_roadmap[s.roadmap_id], s.order, s.id or 0),
        )


class _LineRepo:
    """Реплики в уже заданном порядке проигрывания."""

    def __init__(self, items=()):
        self.items = list(items)

    async def list_by_novel_id(self, novel_id: int):
        return [line for line in self.items if line.novel_id == novel_id]


class _CharacterRepo:
    async def get_by_id(self, character_id: int):
        return None


class _RoadmapChoiceRepo:
    def __init__(self, items=()):
        self.items = list(items)

    async def list_by_novel_id(self, novel_id: int):
        return list(self.items)

    async def list_by_roadmap_id(self, roadmap_id: int):
        return [c for c in self.items if c.roadmap_id == roadmap_id]


class _PlayerChoiceRepo:
    def __init__(self, items=()):
        self.items = list(items)

    async def list_by_novel_id(self, novel_id: int):
        return [c for c in self.items if c.novel_id == novel_id]


class _Lock:
    def __init__(self, locked: bool = False):
        self.locked = locked

    async def is_locked(self, novel_id: int, roadmap_id: int, position: int) -> bool:
        return self.locked


# --- доменные объекты -------------------------------------------------------


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


def _roadmap(
    roadmap_id: int,
    depth: int,
    parent: int | None,
    *,
    target_choice: bool = False,
    scenes_count: int = 1,
) -> Roadmap:
    return Roadmap(
        id=roadmap_id,
        created_at=None,
        updated_at=None,
        novel_id=NOVEL_ID,
        depth=depth,
        title=f"шаг {depth}",
        event="",
        conflict="",
        change="",
        target_choice=target_choice,
        choice_stakes=None,
        scenes_count=scenes_count,
        parent_roadmap_id=parent,
        branch_id=0,
    )


def _scene(
    scene_id: int,
    roadmap_id: int,
    order: int,
    *,
    final_for_novel: bool = False,
    needs_review: bool = False,
) -> Scene:
    return Scene(
        id=scene_id,
        created_at=None,
        updated_at=None,
        roadmap_id=roadmap_id,
        title=f"сцена {order}",
        description="",
        order=order,
        is_final_for_roadmap=True,
        is_final_for_novel=final_for_novel,
        needs_review=needs_review,
    )


def _line(
    line_id: int, scene_id: int, order: int, *, final: bool = False
) -> DialogueLine:
    return DialogueLine(
        id=line_id,
        created_at=None,
        updated_at=None,
        novel_id=NOVEL_ID,
        scene_id=scene_id,
        character_id=None,
        order=order,
        text="реплика",
        is_final_for_scene=final,
        kind=LineKind.NARRATION,
    )


def _choice(
    choice_id: int,
    roadmap_id: int,
    *,
    order: int = 1,
    text: str = "Да",
    is_true: bool = True,
    next_roadmap_id: int | None = None,
) -> RoadmapChoice:
    return RoadmapChoice(
        id=choice_id,
        created_at=None,
        updated_at=None,
        roadmap_id=roadmap_id,
        order=order,
        text=text,
        is_true=is_true,
        next_roadmap_id=next_roadmap_id,
    )


def _service(
    *,
    roadmaps,
    scenes,
    lines,
    choices=(),
    player_choices=(),
    locked: bool = False,
) -> NovelPlaybackService:
    return NovelPlaybackService(
        novel_repository=_ByNovelRepo([_novel()]),
        roadmap_repository=_ByNovelRepo(roadmaps),
        scene_repository=_SceneRepo(scenes, roadmaps),
        dialogue_line_repository=_LineRepo(lines),
        character_repository=_CharacterRepo(),
        roadmap_choice_repository=_RoadmapChoiceRepo(choices),
        player_choice_repository=_PlayerChoiceRepo(player_choices),
        lock=_Lock(locked),
    )


# --- сценарии ---------------------------------------------------------------


class TestTailDoNotFinishWhileSceneHasNoDialogue:
    async def test_choice_step_with_written_scene_but_no_lines_is_generating(self):
        """Сцена записана, реплик нет, задача активна → generating."""
        roadmaps = [_roadmap(10, 1, None), _roadmap(20, 2, 10, target_choice=True)]
        scenes = [_scene(100, 10, 1), _scene(200, 20, 1)]  # сцена 200 без реплик
        lines = [_line(1, 100, 1, final=True)]  # шаг 1 прочитан до конца

        result = await _service(
            roadmaps=roadmaps, scenes=scenes, lines=lines, locked=True
        ).next(NOVEL_ID, 1)

        assert result.status is PlaybackStatus.GENERATING
        assert result.next_roadmap_id == 20
        assert result.next_position == 1

    async def test_choice_step_with_written_scene_but_no_lines_needs_generation(self):
        """Тот же случай без активной задачи → need_generation."""
        roadmaps = [_roadmap(10, 1, None), _roadmap(20, 2, 10, target_choice=True)]
        scenes = [_scene(100, 10, 1), _scene(200, 20, 1)]
        lines = [_line(1, 100, 1, final=True)]

        result = await _service(roadmaps=roadmaps, scenes=scenes, lines=lines).next(
            NOVEL_ID, 1
        )

        assert result.status is PlaybackStatus.NEED_GENERATION
        assert (result.next_roadmap_id, result.next_position) == (20, 1)

    async def test_second_scene_of_step_without_lines_points_at_that_scene(self):
        """Недописанная вторая сцена шага: position — её номер, а не следующий."""
        roadmaps = [_roadmap(10, 1, None, scenes_count=2)]
        scenes = [_scene(100, 10, 1), _scene(101, 10, 2)]
        lines = [_line(1, 100, 1, final=True)]

        result = await _service(roadmaps=roadmaps, scenes=scenes, lines=lines).next(
            NOVEL_ID, 1
        )

        assert result.status is PlaybackStatus.NEED_GENERATION
        assert (result.next_roadmap_id, result.next_position) == (10, 2)

    async def test_incomplete_scene_wins_over_generation_of_the_next_step(self):
        """Недописанная сцена шага важнее генерации следующего шага."""
        roadmaps = [_roadmap(10, 1, None, scenes_count=2), _roadmap(20, 2, 10)]
        scenes = [_scene(100, 10, 1), _scene(101, 10, 2)]  # у 101 ещё нет реплик
        lines = [_line(1, 100, 1, final=True)]

        result = await _service(roadmaps=roadmaps, scenes=scenes, lines=lines).next(
            NOVEL_ID, 1
        )

        assert result.status is PlaybackStatus.NEED_GENERATION
        assert (result.next_roadmap_id, result.next_position) == (10, 2)

    async def test_choice_line_is_served_once_dialogue_is_written(self):
        """После записи реплик отдаётся реплика-развилка, а не финал."""
        roadmaps = [_roadmap(10, 1, None), _roadmap(20, 2, 10, target_choice=True)]
        scenes = [_scene(100, 10, 1), _scene(200, 20, 1)]
        lines = [
            _line(1, 100, 1, final=True),
            _line(2, 200, 1, final=True),
        ]
        choices = [_choice(500, 20)]

        result = await _service(
            roadmaps=roadmaps, scenes=scenes, lines=lines, choices=choices
        ).next(NOVEL_ID, 1)

        assert result.status is PlaybackStatus.CHOICE
        assert result.step is not None and result.step.dialogue.id == 2
        assert [c.id for c in result.choices] == [500]

    async def test_finished_only_when_every_scene_on_path_has_lines(self):
        """Все сцены пути дописаны и шаги закрыты → настоящий финал."""
        roadmaps = [_roadmap(10, 1, None), _roadmap(20, 2, 10)]
        scenes = [_scene(100, 10, 1), _scene(200, 20, 1, final_for_novel=True)]
        lines = [_line(1, 100, 1, final=True), _line(2, 200, 1, final=True)]

        result = await _service(roadmaps=roadmaps, scenes=scenes, lines=lines).next(
            NOVEL_ID, 2
        )

        assert result.status is PlaybackStatus.FINISHED

    async def test_next_step_without_scene_still_needs_generation(self):
        """Обычный случай «следующей сцены ещё нет» не изменился."""
        roadmaps = [_roadmap(10, 1, None), _roadmap(20, 2, 10)]
        scenes = [_scene(100, 10, 1)]
        lines = [_line(1, 100, 1, final=True)]

        result = await _service(roadmaps=roadmaps, scenes=scenes, lines=lines).next(
            NOVEL_ID, 1
        )

        assert result.status is PlaybackStatus.NEED_GENERATION
        assert (result.next_roadmap_id, result.next_position) == (20, 1)

    async def test_review_scene_does_not_mask_incomplete_scene(self):
        """needs_review-сцена не считается: шаг всё ещё ждёт генерацию."""
        roadmaps = [_roadmap(10, 1, None, scenes_count=1)]
        scenes = [_scene(100, 10, 1, needs_review=True)]
        lines: list[DialogueLine] = []

        result = await _service(roadmaps=roadmaps, scenes=scenes, lines=lines).next(
            NOVEL_ID, None
        )

        assert result.status is PlaybackStatus.NEED_GENERATION
        assert (result.next_roadmap_id, result.next_position) == (10, 1)
