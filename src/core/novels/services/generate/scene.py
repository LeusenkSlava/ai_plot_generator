import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces import GeneratorProtocol
from src.core.novels.models import Novel, Roadmap, Scene
from src.core.novels.services.crud import NovelService, RoadmapService, SceneService
from src.core.novels.services.generate.base import BaseGenerator

logger = logging.getLogger(__name__)


class SceneGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        roadmap_service: RoadmapService,
        scene_service: SceneService,
        generator: GeneratorProtocol,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service
        self._scene_service = scene_service

    async def generate(
        self, roadmap_id: int, previous_scenes: list[Scene] | None = None
    ) -> Scene:
        """Следующая сцена шага роадмапа. previous_scenes — уже сыгранные сцены новеллы для связности."""
        roadmap = await self._roadmap_service.get(roadmap_id)
        if not roadmap:
            raise GenerationError(f"Roadmap with id {roadmap_id} not found")

        novel = await self._novel_service.get(roadmap.novel_id)
        if not novel:
            raise GenerationError(f"Novel with id {roadmap.novel_id} not found")

        existing = await self._scene_service.list_by_roadmap(roadmap.id) or []
        order = len(existing) + 1
        is_final_for_roadmap = order >= max(roadmap.scenes_count, 1)
        roadmaps = await self._roadmap_service.list_by_novel(novel.id) or []
        is_last_roadmap = roadmap.step_id >= max((r.step_id for r in roadmaps), default=0)

        prompt = self.__create_prompt(novel, roadmap, order, previous_scenes or [])
        data = await self._generate(prompt)

        scene = Scene(
            id=None,
            created_at=None,
            updated_at=None,
            roadmap_id=roadmap.id,
            title=data["title"],
            description=data["description"],
            order=order,
            is_final_for_roadmap=is_final_for_roadmap,
            is_final_for_novel=is_final_for_roadmap and is_last_roadmap,
        )
        scene = await self._scene_service.add(scene)
        return scene

    def __create_prompt(
        self, novel: Novel, roadmap: Roadmap, order: int, previous_scenes: list[Scene]
    ) -> list[dict]:
        scenes_count = max(roadmap.scenes_count, order)
        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания истории и текущего шага роадмапа создай очередную сцену этого шага. "
                "Она должна продолжать предыдущие сцены, не повторяя их, "
                "и продвигать сюжет к цели шага. "
                "Сцена должна раскрывать цель шага и задавать место и ситуацию действия, "
                "но не пересказывать сами диалоги. Укажи:\n"
                "1. title - короткое название сцены.\n"
                "2. description - описание места, ситуации и настроения сцены, "
                "на основе которого дальше будут сгенерированы диалоги персонажей.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "title": string,
                  "description": string
                }
                """
            ),
        }
        user_prompt = {
            "role": "user",
            "content": (
                f"Название истории: {novel.title}\n"
                f"Тон повествования: {novel.tone}\n"
                f"Шаг роадмапа: {roadmap.title}\n"
                f"Цель шага: {roadmap.goal}\n"
                f"Номер сцены в шаге: {order} из {scenes_count}"
            ),
        }
        if previous_scenes:
            story_so_far = "\n".join(
                f"- {scene.title}: {scene.description}" for scene in previous_scenes
            )
            user_prompt["content"] += f"\n\nПредыдущие сцены:\n{story_so_far}"
        return [system_prompt, user_prompt]
