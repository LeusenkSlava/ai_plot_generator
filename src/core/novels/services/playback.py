from dataclasses import dataclass
from enum import Enum

from src.core.novels.exceptions import (
    CharacterNotFoundError,
    DialogueLineNotFoundError,
    NovelNotFoundError,
    SceneNotFoundError,
)
from src.core.novels.interfaces.generation import SceneGenerationLockProtocol
from src.core.novels.interfaces.repository import (
    CharacterRepositoryProtocol,
    DialogueLineRepositoryProtocol,
    NovelRepositoryProtocol,
    RoadmapRepositoryProtocol,
    SceneRepositoryProtocol,
)
from src.core.novels.models import Character, DialogueLine, Scene
from src.core.novels.services.state import resolve_next_slot


class PlaybackStatus(str, Enum):
    OK = "ok"
    NEED_GENERATION = "need_generation"
    GENERATING = "generating"
    FINISHED = "finished"


@dataclass(frozen=True, slots=True)
class DialogueStep:
    dialogue: DialogueLine
    scene: Scene
    character: Character


@dataclass(frozen=True, slots=True)
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
        """Следующая реплика за dialogue_line_id.

        dialogue_line_id=None — начать с начала новеллы.
        Если реплики кончились — вернуть статус finished / need_generation / generating.
        """
        if await self._novels.get_by_id(novel_id) is None:
            raise NovelNotFoundError(novel_id)

        lines = await self._dialogue_lines.list_by_novel_id(novel_id)

        index = self._resolve_index(lines, dialogue_line_id)

        if index < len(lines):
            return PlaybackResult(
                status=PlaybackStatus.OK,
                step=await self._step(lines[index]),
            )

        return await self._resolve_tail_status(novel_id)

    @staticmethod
    def _resolve_index(lines: list[DialogueLine], dialogue_line_id: int | None) -> int:
        if dialogue_line_id is None:
            return 0
        position = next(
            (i for i, line in enumerate(lines) if line.id == dialogue_line_id),
            None,
        )
        if position is None:
            raise DialogueLineNotFoundError(dialogue_line_id)
        return position + 1

    async def _resolve_tail_status(self, novel_id: int) -> PlaybackResult:
        roadmaps = await self._roadmaps.list_by_novel_id(novel_id)
        scenes = await self._scenes.list_by_novel_id(novel_id)
        slot = resolve_next_slot(roadmaps, scenes)
        if slot is None:
            return PlaybackResult(status=PlaybackStatus.FINISHED)

        status = (
            PlaybackStatus.GENERATING
            if await self._lock.is_locked(novel_id, slot.order)
            else PlaybackStatus.NEED_GENERATION
        )
        return PlaybackResult(status=status, next_scene_order=slot.order)

    async def _step(self, line: DialogueLine) -> DialogueStep:
        scene = await self._scenes.get_by_id(line.scene_id)
        if scene is None:
            raise SceneNotFoundError(line.scene_id)
        character = await self._characters.get_by_id(line.character_id)
        if character is None:
            raise CharacterNotFoundError(line.character_id)
        return DialogueStep(dialogue=line, scene=scene, character=character)
