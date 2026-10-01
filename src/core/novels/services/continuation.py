import logging

from src.core.novels.models import DialogueLine, Scene
from src.core.novels.services.crud import RoadmapService, SceneService
from src.core.novels.services.generate.dialogue import DialogueGenerator
from src.core.novels.services.generate.scene import SceneGenerator

logger = logging.getLogger(__name__)

# Сколько контекста передаём LLM для связности продолжения
PREVIOUS_SCENES_LIMIT = 5
PREVIOUS_LINES_LIMIT = 10


class NovelContinuationService:
    """Догенерация новеллы: следующая сцена текущего шага роадмапа или первая сцена следующего шага."""

    def __init__(
        self,
        roadmap_service: RoadmapService,
        scene_service: SceneService,
        scene_generator: SceneGenerator,
        dialogue_generator: DialogueGenerator,
    ):
        self._roadmap_service = roadmap_service
        self._scene_service = scene_service
        self._scene_generator = scene_generator
        self._dialogue_generator = dialogue_generator

    async def continue_story(
        self, novel_id: int, previous_lines: list[DialogueLine]
    ) -> list[DialogueLine]:
        """Генерирует следующую сцену с диалогом. Пустой список — роадмап пройден, новелла закончилась."""
        previous_scenes: list[Scene] = []
        for roadmap in await self._roadmap_service.list_by_novel(novel_id) or []:
            scenes = await self._scene_service.list_by_roadmap(roadmap.id) or []
            if len(scenes) < max(roadmap.scenes_count, 1):
                logger.info(
                    f"NovelContinuationService: novel {novel_id}, step {roadmap.step_id}, "
                    f"scene {len(scenes) + 1}/{roadmap.scenes_count}"
                )
                scene = await self._scene_generator.generate(
                    roadmap.id, previous_scenes=(previous_scenes + scenes)[-PREVIOUS_SCENES_LIMIT:]
                )
                return await self._dialogue_generator.generate(
                    scene.id, previous_lines=previous_lines[-PREVIOUS_LINES_LIMIT:]
                )
            previous_scenes.extend(scenes)
        return []
