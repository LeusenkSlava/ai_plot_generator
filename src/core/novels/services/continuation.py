import logging

from src.core.novels.exceptions import (
    NovelFinishedError,
    NovelNotFoundError,
    SceneOrderError,
)
from src.core.novels.interfaces import (
    DialogueLineRepositoryProtocol,
    NovelRepositoryProtocol,
    RoadmapRepositoryProtocol,
    SceneGenerationLockProtocol,
    SceneRepositoryProtocol,
)
from src.core.novels.models import Roadmap, Scene
from src.core.novels.services.generate.dialogue import DialogueGenerator
from src.core.novels.services.generate.scene import SceneGenerator
from src.core.novels.services.generate.story_context import StoryContextGenerator

logger = logging.getLogger(__name__)

# Сколько контекста передаём LLM для связности продолжения
PREVIOUS_SCENES_LIMIT = 5
PREVIOUS_LINES_LIMIT = 10


def next_scene_order(
    roadmaps: list[Roadmap], scenes: list[Scene]
) -> int | None:
    """Порядковый номер (с 1, сквозной по новелле) следующей сцены. None — роадмап пройден."""
    scenes_by_roadmap: dict[int, int] = {}
    for scene in scenes:
        scenes_by_roadmap[scene.roadmap_id] = scenes_by_roadmap.get(scene.roadmap_id, 0) + 1
    for roadmap in roadmaps:
        if scenes_by_roadmap.get(roadmap.id, 0) < max(roadmap.scenes_count, 1):
            return len(scenes) + 1
    return None


def _next_roadmap(roadmaps: list[Roadmap], scenes: list[Scene]) -> Roadmap | None:
    """Шаг роадмапа, в который попадёт следующая сцена."""
    for roadmap in roadmaps:
        count = sum(1 for scene in scenes if scene.roadmap_id == roadmap.id)
        if count < max(roadmap.scenes_count, 1):
            return roadmap
    return None


class SceneContinuationService:
    """Догенерация новеллы: сцена с порядковым номером scene_order вместе с репликами.

    Идемпотентна по (novel_id, scene_order): уже сгенерированная сцена возвращается как есть,
    параллельная генерация той же сцены ждёт завершения первой через блокировку.
    """

    def __init__(
        self,
        novel_repository: NovelRepositoryProtocol,
        roadmap_repository: RoadmapRepositoryProtocol,
        scene_repository: SceneRepositoryProtocol,
        dialogue_line_repository: DialogueLineRepositoryProtocol,
        scene_generator: SceneGenerator,
        dialogue_generator: DialogueGenerator,
        story_context_generator: StoryContextGenerator,
        lock: SceneGenerationLockProtocol,
    ):
        self._novels = novel_repository
        self._roadmaps = roadmap_repository
        self._scenes = scene_repository
        self._dialogue_lines = dialogue_line_repository
        self._scene_generator = scene_generator
        self._dialogue_generator = dialogue_generator
        self._story_context_generator = story_context_generator
        self._lock = lock

    async def generate(self, novel_id: int, scene_order: int) -> tuple[Scene, bool]:
        """Возвращает (сцена, создана ли она сейчас).

        Вызывающий должен закоммитить транзакцию: блокировка держится до её конца.
        """
        if await self._novels.get_by_id(novel_id) is None:
            raise NovelNotFoundError(novel_id)

        logger.info(
            "Scene generation: novel_id=%s scene_order=%s waiting for lock",
            novel_id,
            scene_order,
        )
        await self._lock.acquire(novel_id, scene_order)

        # Читаем состояние только после блокировки: параллельная генерация уже закоммичена
        roadmaps = await self._roadmaps.list_by_novel_id(novel_id)
        scenes = await self._scenes.list_by_novel_id(novel_id)

        if scene_order <= len(scenes):
            scene = scenes[scene_order - 1]
            logger.info(
                "Scene generation: novel_id=%s scene_order=%s already exists, scene_id=%s",
                novel_id,
                scene_order,
                scene.id,
            )
            return scene, False

        expected = next_scene_order(roadmaps, scenes)
        if expected is None:
            raise NovelFinishedError(novel_id)
        if scene_order != expected:
            raise SceneOrderError(novel_id, scene_order, expected)

        roadmap = _next_roadmap(roadmaps, scenes)
        # Изложение истории после последней сцены, у которой оно есть
        story_context = next(
            (s.story_context for s in reversed(scenes) if s.story_context), None
        )
        logger.info(
            "Scene generation: novel_id=%s scene_order=%s generating scene, step_id=%s",
            novel_id,
            scene_order,
            roadmap.step_id,
        )
        scene = await self._scene_generator.generate(
            roadmap.id,
            previous_scenes=scenes[-PREVIOUS_SCENES_LIMIT:],
            story_context=story_context,
        )

        logger.info(
            "Scene generation: novel_id=%s scene_order=%s generating dialogue, scene_id=%s",
            novel_id,
            scene_order,
            scene.id,
        )
        previous_lines = await self._dialogue_lines.list_by_novel_id(novel_id)
        previous_lines = [line for line in previous_lines if line.scene_id != scene.id]
        await self._dialogue_generator.generate(
            scene.id,
            previous_lines=previous_lines[-PREVIOUS_LINES_LIMIT:],
            story_context=story_context,
        )

        logger.info(
            "Scene generation: novel_id=%s scene_order=%s updating story context, scene_id=%s",
            novel_id,
            scene_order,
            scene.id,
        )
        await self._story_context_generator.generate(
            scene.id, previous_context=story_context
        )

        logger.info(
            "Scene generation: novel_id=%s scene_order=%s generated, scene_id=%s",
            novel_id,
            scene_order,
            scene.id,
        )
        return scene, True
