"""Проигрывание после развилки идёт по выбранной ветке, а не по плоскому списку.

Регрессия: ``NovelPlaybackService.next`` брал все реплики новеллы, отсортированные
по ``branch_id``/``depth``, поэтому после выбора альтернативы клиент продолжал
получать ранее пройденную (истинную) ветку.
"""

import pytest

from src.core.novels.exceptions import DialogueLineNotFoundError
from src.core.novels.models import (
    DialogueLine,
    LineKind,
    Novel,
    PlayerChoice,
    Roadmap,
    RoadmapChoice,
    Scene,
)
from src.core.novels.services.playback import NovelPlaybackService, PlaybackStatus

NOVEL_ID = 7


class _ByNovelRepo:
    """Репозиторий с id и novel_id (новеллы, реплики, выборы игрока)."""

    def __init__(self, items=()):
        self.items = list(items)

    async def get_by_id(self, item_id: int, author_id: int | None = None):
        item = next((i for i in self.items if i.id == item_id), None)
        if item is None:
            return None
        if author_id is not None and getattr(item, "author_id", None) != author_id:
            return None
        return item

    async def list_by_novel_id(self, novel_id: int):
        return [i for i in self.items if i.novel_id == novel_id]


class _SceneRepo(_ByNovelRepo):
    """Сцены в порядке, заданном тестом."""

    async def list_by_novel_id(self, novel_id: int):
        return list(self.items)


class _RoadmapChoiceRepo(_ByNovelRepo):
    async def list_by_novel_id(self, novel_id: int):
        return list(self.items)

    async def list_by_roadmap_id(self, roadmap_id: int):
        return [c for c in self.items if c.roadmap_id == roadmap_id]


class _CharacterRepo:
    async def get_by_id(self, character_id: int):
        return None


class _Lock:
    async def is_locked(self, novel_id: int, roadmap_id: int, position: int) -> bool:
        return False


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
    branch_id: int = 0,
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
        scenes_count=1,
        parent_roadmap_id=parent,
        branch_id=branch_id,
    )


def _scene(
    scene_id: int,
    roadmap_id: int,
    order: int,
    *,
    final_for_roadmap: bool = False,
) -> Scene:
    return Scene(
        id=scene_id,
        created_at=None,
        updated_at=None,
        roadmap_id=roadmap_id,
        title=f"сцена {order}",
        description="",
        order=order,
        is_final_for_roadmap=final_for_roadmap,
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
    next_roadmap_id: int | None,
    is_true: bool,
) -> RoadmapChoice:
    return RoadmapChoice(
        id=choice_id,
        created_at=None,
        updated_at=None,
        roadmap_id=roadmap_id,
        order=1,
        text="вариант",
        is_true=is_true,
        next_roadmap_id=next_roadmap_id,
    )


def _player_choice(player_choice_id: int, choice_id: int) -> PlayerChoice:
    return PlayerChoice(
        id=player_choice_id,
        created_at=None,
        updated_at=None,
        novel_id=NOVEL_ID,
        roadmap_choice_id=choice_id,
    )


def _service(
    *,
    roadmaps,
    scenes,
    lines,
    choices=(),
    player_choices=(),
) -> NovelPlaybackService:
    return NovelPlaybackService(
        novel_repository=_ByNovelRepo([_novel()]),
        roadmap_repository=_ByNovelRepo(roadmaps),
        scene_repository=_SceneRepo(scenes),
        dialogue_line_repository=_ByNovelRepo(lines),
        character_repository=_CharacterRepo(),
        roadmap_choice_repository=_RoadmapChoiceRepo(choices),
        player_choice_repository=_ByNovelRepo(player_choices),
        lock=_Lock(),
    )


def _world(player_choices) -> NovelPlaybackService:
    """Корень -> развилка 20 -> истинная ветка 30 / альтернатива 40.

    В плоском списке реплик истинная ветка (id 3) идёт раньше альтернативы (id 4),
    поэтому именно она раньше возвращалась после выбора форка.
    """
    roadmaps = [
        _roadmap(10, 1, None),
        _roadmap(20, 2, 10, target_choice=True),
        _roadmap(30, 3, 20),
        _roadmap(40, 3, 20, branch_id=1),
    ]
    scenes = [
        _scene(100, 10, 1),
        _scene(200, 20, 1, final_for_roadmap=True),
        _scene(300, 30, 1),
        _scene(400, 40, 1),
    ]
    lines = [
        _line(1, 100, 1, final=True),
        _line(2, 200, 1, final=True),
        _line(3, 300, 1),
        _line(4, 400, 1),
    ]
    choices = [
        _choice(500, 20, next_roadmap_id=30, is_true=True),
        _choice(501, 20, next_roadmap_id=40, is_true=False),
    ]
    return _service(
        roadmaps=roadmaps,
        scenes=scenes,
        lines=lines,
        choices=choices,
        player_choices=player_choices,
    )


class TestPlaybackFollowsChosenBranch:
    async def test_after_choice_returns_alternative_branch_not_true_branch(self):
        """После выбора альтернативы отдаётся её реплика, а не продолжение истинной."""
        service = _world([_player_choice(1, 501)])

        result = await service.next(NOVEL_ID, 2)

        assert result.status is PlaybackStatus.OK
        assert result.step is not None
        assert result.step.dialogue.id == 4

    async def test_after_choice_returns_true_branch_when_it_is_chosen(self):
        """Если выбрана истинная ветка, отдаётся её продолжение."""
        service = _world([_player_choice(1, 500)])

        result = await service.next(NOVEL_ID, 2)

        assert result.status is PlaybackStatus.OK
        assert result.step is not None
        assert result.step.dialogue.id == 3

    async def test_latest_choice_wins_on_replay(self):
        """В журнале остались оба выбора: путь идёт по последнему (альтернатива)."""
        service = _world([_player_choice(1, 500), _player_choice(2, 501)])

        result = await service.next(NOVEL_ID, 2)

        assert result.status is PlaybackStatus.OK
        assert result.step is not None
        assert result.step.dialogue.id == 4

    async def test_choice_line_is_served_from_branch_path(self):
        """Реплика развилки отдаётся как choice, и это последняя реплика форка."""
        service = _world([_player_choice(1, 501)])

        result = await service.next(NOVEL_ID, 1)

        assert result.status is PlaybackStatus.CHOICE
        assert result.step is not None
        assert result.step.dialogue.id == 2
        assert [c.id for c in result.choices or []] == [500, 501]

    async def test_stale_offset_from_switched_branch_restarts_path(self):
        """Offset с прежней ветки не даёт 404: чтение пути начинается заново."""
        service = _world([_player_choice(1, 501)])

        result = await service.next(NOVEL_ID, 3)

        assert result.status is PlaybackStatus.OK
        assert result.step is not None
        assert result.step.dialogue.id == 1

    async def test_unknown_offset_still_raises_not_found(self):
        """Несуществующий id реплики по-прежнему 404."""
        service = _world([_player_choice(1, 501)])

        with pytest.raises(DialogueLineNotFoundError):
            await service.next(NOVEL_ID, 999)
