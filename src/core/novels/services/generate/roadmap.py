import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces import GeneratorProtocol
from src.core.novels.models import Novel, Roadmap
from src.core.novels.services.crud import NovelService, RoadmapService
from src.core.novels.services.generate.base import BaseGenerator

logger = logging.getLogger(__name__)


class RoadmapGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        roadmap_service: RoadmapService,
        generator: GeneratorProtocol,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service

    async def generate(self, novel_id: int) -> list[Roadmap]:
        novel = await self._novel_service.get(novel_id)
        if not novel:
            raise GenerationError(f"Novel with id {novel_id} not found")

        prompt = self.__create_prompt(novel)
        data = await self._generate(prompt)

        roadmap_data = data.get("roadmap")
        if not roadmap_data:
            raise GenerationError("Generator returned no roadmap")

        roadmap = []
        for step_id, item in enumerate(roadmap_data, start=1):
            step = Roadmap(
                id=None,
                created_at=None,
                updated_at=None,
                novel_id=novel.id,
                step_id=step_id,
                title=item["title"],
                goal=item["goal"],
                target_choice=item["target_choice"],
                choice_stakes=item.get("choice_stakes"),
                scenes_count=item["scenes_count"],
            )
            step = await self._roadmap_service.add(step)
            roadmap.append(step)

        return roadmap

    def __create_prompt(self, novel: Novel) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания истории и её тона создай роадмап сюжета — "
                "последовательность шагов, из которых складывается ветвящаяся история. "
                "Количество шагов определи сам исходя из масштаба истории — обычно от 3 до 8. "
                "Для каждого шага укажи:\n"
                "1. title - короткое название шага.\n"
                "2. goal - что должно произойти в сюжете на этом шаге.\n"
                "3. target_choice - true, если шаг заканчивается развилкой, где игрок делает значимый выбор, иначе false.\n"
                "4. choice_stakes - если target_choice true, кратко опиши, что поставлено на карту при этом выборе, иначе null.\n"
                "5. scenes_count - сколько сцен потребуется, чтобы раскрыть этот шаг (обычно от 1 до 4).\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "roadmap": [
                    {
                      "title": string,
                      "goal": string,
                      "target_choice": boolean,
                      "choice_stakes": string | null,
                      "scenes_count": integer
                    }
                  ]
                }
                """
            ),
        }
        user_prompt = {
            "role": "user",
            "content": (
                f"Название: {novel.title}\n"
                f"Описание: {novel.description}\n"
                f"Тон повествования: {novel.tone}"
            ),
        }
        return [system_prompt, user_prompt]
