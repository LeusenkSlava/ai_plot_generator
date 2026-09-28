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

    async def generate(self, roadmap_id: int) -> Scene:
        roadmap = await self._roadmap_service.get(roadmap_id)
        if not roadmap:
            raise GenerationError(f"Roadmap with id {roadmap_id} not found")

        novel = await self._novel_service.get(roadmap.novel_id)
        if not novel:
            raise GenerationError(f"Novel with id {roadmap.novel_id} not found")

        prompt = self.__create_prompt(novel, roadmap)
        data = await self._generate(prompt)

        scene = Scene(
            id=None,
            created_at=None,
            updated_at=None,
            roadmap_id=roadmap.id,
            title=data["title"],
            description=data["description"],
            order=1,
        )
        scene = await self._scene_service.add(scene)
        return scene

    def __create_prompt(self, novel: Novel, roadmap: Roadmap) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания истории и текущего шага роадмапа создай первую сцену этого шага. "
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
                f"Цель шага: {roadmap.goal}"
            ),
        }
        return [system_prompt, user_prompt]
