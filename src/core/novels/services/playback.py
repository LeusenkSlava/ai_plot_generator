from dataclasses import dataclass

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
    SceneRepositoryProtocol,
)
from src.core.novels.models import Character, DialogueLine, Scene
from src.core.novels.services.continuation import NovelContinuationService


@dataclass
class DialogueStep:
    dialogue: DialogueLine
    scene: Scene
    character: Character


class NovelPlaybackService:
    """Проигрывание новеллы: выдаёт реплики по порядку вместе с персонажем.

    Когда сгенерированные реплики заканчиваются, а роадмап ещё не пройден, догенерирует следующую сцену.
    """

    def __init__(
        self,
        novel_repository: NovelRepositoryProtocol,
        roadmap_repository: RoadmapRepositoryProtocol,
        scene_repository: SceneRepositoryProtocol,
        dialogue_line_repository: DialogueLineRepositoryProtocol,
        character_repository: CharacterRepositoryProtocol,
        continuation_service: NovelContinuationService,
    ):
        self._novels = novel_repository
        self._roadmaps = roadmap_repository
        self._scenes = scene_repository
        self._dialogue_lines = dialogue_line_repository
        self._characters = character_repository
        self._continuation = continuation_service

    async def start(self, novel_id: int) -> DialogueStep | None:
        """Первая реплика новеллы. None — если в новелле нет реплик."""
        return await self.next(novel_id, None)

    async def next(
        self, novel_id: int, dialogue_line_id: int | None
    ) -> DialogueStep | None:
        """Реплика, следующая за dialogue_line_id (offset).

        dialogue_line_id=None — начать с начала. None в ответе — новелла закончилась
        (реплики кончились и весь роадмап пройден).
        """
        lines = await self._ordered_lines(novel_id)

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
            line = lines[index]
        else:
            new_lines = await self._continuation.continue_story(novel_id, lines)
            if not new_lines:
                return None
            line = new_lines[0]

        scene = await self._scenes.get_by_id(line.scene_id)
        if scene is None:
            raise SceneNotFoundError(line.scene_id)
        character = await self._characters.get_by_id(line.character_id)
        if character is None:
            raise CharacterNotFoundError(line.character_id)
        return DialogueStep(dialogue=line, scene=scene, character=character)

    async def _ordered_lines(self, novel_id: int) -> list[DialogueLine]:
        """Все реплики новеллы: роадмап (step_id) -> сцена (order) -> реплика (order)."""
        if await self._novels.get_by_id(novel_id) is None:
            raise NovelNotFoundError(novel_id)

        lines: list[DialogueLine] = []
        for roadmap in await self._roadmaps.list_by_novel_id(novel_id):
            for scene in await self._scenes.list_by_roadmap_id(roadmap.id):
                lines.extend(await self._dialogue_lines.list_by_scene_id(scene.id))
        return lines
