from dataclasses import dataclass
from typing import Literal

from src.core.novels.exceptions import (
    CharacterNotFoundError,
    DialogueLineNotFoundError,
    NovelNotFoundError,
    SceneNotFoundError,
)
from src.core.novels.interfaces import (
    CharacterRepositoryProtocol,
    DialogueLineRepositoryProtocol,
    NovelRepositoryProtocol,
    RoadmapRepositoryProtocol,
    SceneGenerationLockProtocol,
    SceneRepositoryProtocol,
)
from src.core.novels.models import Character, DialogueLine, Scene
from src.core.novels.services.continuation import next_scene_order


@dataclass
class DialogueStep:
    dialogue: DialogueLine
    scene: Scene
    character: Character


PlaybackStatus = Literal["ok", "need_generation", "generating", "finished"]


@dataclass
class PlaybackResult:
    status: PlaybackStatus
    step: DialogueStep | None = None
    next_scene_order: int | None = None


class NovelPlaybackService:
    """Проигрывание новеллы: выдаёт реплики по порядку вместе с персонажем.

    Только читает из БД. Если реплики кончились, а роадмап не пройден, сообщает номер сцены,
    которую нужно сгенерировать (генерация идёт через Kafka).
    """

    def __init__(
        self,
        novel_repository: NovelRepositoryProtocol,
        roadmap_repository: RoadmapRepositoryProtocol,
        scene_repository: SceneRepositoryProtocol,
        dialogue_line_repository: DialogueLineRepositoryProtocol,
        character_repository: CharacterRepositoryProtocol,
        lock: SceneGenerationLockProtocol,
    ):
        self._novels = novel_repository
        self._roadmaps = roadmap_repository
        self._scenes = scene_repository
        self._dialogue_lines = dialogue_line_repository
        self._characters = character_repository
        self._lock = lock

    async def next(self, novel_id: int, dialogue_line_id: int | None) -> PlaybackResult:
        """Реплика, следующая за dialogue_line_id (offset); None — начать с начала."""
        if await self._novels.get_by_id(novel_id) is None:
            raise NovelNotFoundError(novel_id)
        lines = await self._dialogue_lines.list_by_novel_id(novel_id)

        if dialogue_line_id is None:
            index = 0
        else:
            position = next(
                (i for i, line in enumerate(lines) if line.id == dialogue_line_id),
                None,
            )
            if position is None:
                raise DialogueLineNotFoundError(dialogue_line_id)
            index = position + 1

        if index < len(lines):
            return PlaybackResult(status="ok", step=await self._step(lines[index]))

        roadmaps = await self._roadmaps.list_by_novel_id(novel_id)
        scenes = await self._scenes.list_by_novel_id(novel_id)
        order = next_scene_order(roadmaps, scenes)
        if order is None:
            return PlaybackResult(status="finished")
        status = "generating" if await self._lock.is_locked(novel_id, order) else "need_generation"
        return PlaybackResult(status=status, next_scene_order=order)

    async def _step(self, line: DialogueLine) -> DialogueStep:
        scene = await self._scenes.get_by_id(line.scene_id)
        if scene is None:
            raise SceneNotFoundError(line.scene_id)
        character = await self._characters.get_by_id(line.character_id)
        if character is None:
            raise CharacterNotFoundError(line.character_id)
        return DialogueStep(dialogue=line, scene=scene, character=character)
