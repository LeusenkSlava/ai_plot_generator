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
    PlayerChoiceRepositoryProtocol,
    RoadmapChoiceRepositoryProtocol,
    RoadmapRepositoryProtocol,
    SceneRepositoryProtocol,
)
from src.core.novels.models import Character, DialogueLine, RoadmapChoice, Scene
from src.core.novels.services.generation.state import resolve_next_slot


class PlaybackStatus(str, Enum):
    OK = "ok"
    CHOICE = "choice"
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
    choices: list[RoadmapChoice] | None = None
    next_roadmap_id: int | None = None
    next_position: int | None = None


class NovelPlaybackService:
    """Проигрывание новеллы: выдаёт реплики по порядку вместе с персонажем.

    Только читает из БД. Если реплики кончились, а роадмап не пройден, сообщает шаг
    роадмапа и позицию сцены, которую нужно сгенерировать (генерация идёт через
    Kafka). На реплике выбора возвращает статус ``choice`` со списком вариантов.
    """

    def __init__(
        self,
        novel_repository: NovelRepositoryProtocol,
        roadmap_repository: RoadmapRepositoryProtocol,
        scene_repository: SceneRepositoryProtocol,
        dialogue_line_repository: DialogueLineRepositoryProtocol,
        character_repository: CharacterRepositoryProtocol,
        roadmap_choice_repository: RoadmapChoiceRepositoryProtocol,
        player_choice_repository: PlayerChoiceRepositoryProtocol,
        lock: SceneGenerationLockProtocol,
    ):
        self._novels = novel_repository
        self._roadmaps = roadmap_repository
        self._scenes = scene_repository
        self._dialogue_lines = dialogue_line_repository
        self._characters = character_repository
        self._roadmap_choices = roadmap_choice_repository
        self._player_choices = player_choice_repository
        self._lock = lock

    async def next(self, novel_id: int, dialogue_line_id: int | None) -> PlaybackResult:
        """Следующая реплика за dialogue_line_id.

        dialogue_line_id=None — начать с начала новеллы.
        Если реплики кончились — вернуть статус finished / need_generation / generating.
        """
        if await self._novels.get_by_id(novel_id) is None:
            raise NovelNotFoundError(novel_id)

        lines = await self._dialogue_lines.list_by_novel_id(novel_id)
        lines = await self._exclude_review_lines(novel_id, lines)

        index = self._resolve_index(lines, dialogue_line_id)

        if index < len(lines):
            line = lines[index]
            step = await self._step(line)
            if await self._is_choice_line(line, step.scene):
                choices = await self._roadmap_choices.list_by_roadmap_id(
                    step.scene.roadmap_id
                )
                return PlaybackResult(
                    status=PlaybackStatus.CHOICE, step=step, choices=choices
                )
            return PlaybackResult(status=PlaybackStatus.OK, step=step)

        return await self._resolve_tail_status(novel_id)

    async def _exclude_review_lines(
        self, novel_id: int, lines: list[DialogueLine]
    ) -> list[DialogueLine]:
        """Отбрасывает реплики сцен, не прошедших смысловую проверку (needs_review).

        Такая сцена не должна показываться игроку: её реплики пропускаются, а шаг
        остаётся незакрытым, чтобы сцена была перегенерирована.
        """
        scenes = await self._scenes.list_by_novel_id(novel_id)
        review_scene_ids = {scene.id for scene in scenes if scene.needs_review}
        if not review_scene_ids:
            return lines
        return [line for line in lines if line.scene_id not in review_scene_ids]

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

    async def _is_choice_line(self, line: DialogueLine, scene: Scene) -> bool:
        """Реплика выбора = последняя реплика последней сцены шага с target_choice."""
        if not line.is_final_for_scene or not scene.is_final_for_roadmap:
            return False
        roadmap = await self._roadmaps.get_by_id(scene.roadmap_id)
        return roadmap is not None and roadmap.target_choice

    async def _resolve_tail_status(self, novel_id: int) -> PlaybackResult:
        roadmaps = await self._roadmaps.list_by_novel_id(novel_id)
        scenes = await self._scenes.list_by_novel_id(novel_id)
        choices = await self._roadmap_choices.list_by_novel_id(novel_id)
        player_choices = await self._player_choices.list_by_novel_id(novel_id)
        slot = resolve_next_slot(roadmaps, scenes, choices, player_choices)
        if slot is None:
            return PlaybackResult(status=PlaybackStatus.FINISHED)

        status = (
            PlaybackStatus.GENERATING
            if await self._lock.is_locked(novel_id, slot.roadmap.id, slot.position)
            else PlaybackStatus.NEED_GENERATION
        )
        return PlaybackResult(
            status=status,
            next_roadmap_id=slot.roadmap.id,
            next_position=slot.position,
        )

    async def _step(self, line: DialogueLine) -> DialogueStep:
        scene = await self._scenes.get_by_id(line.scene_id)
        if scene is None:
            raise SceneNotFoundError(line.scene_id)
        character = await self._characters.get_by_id(line.character_id)
        if character is None:
            raise CharacterNotFoundError(line.character_id)
        return DialogueStep(dialogue=line, scene=scene, character=character)
