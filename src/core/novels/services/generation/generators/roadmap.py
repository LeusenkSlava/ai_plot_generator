import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Character, Novel, Roadmap
from src.core.novels.services.crud import (
    CharacterService,
    NovelService,
    RoadmapService,
)
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.prompts.cast import find_protagonist, render_cast

logger = logging.getLogger(__name__)


class RoadmapGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        roadmap_service: RoadmapService,
        character_service: CharacterService,
        generator: GeneratorProtocol,
        reasoning_effort: str | None = None,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service
        self._character_service = character_service
        self._reasoning_effort = reasoning_effort

    async def generate(self, novel_id: int) -> list[Roadmap]:
        novel = await self._novel_service.get(novel_id)
        if not novel:
            raise GenerationError(f"Novel with id {novel_id} not found")

        characters = await self._character_service.list_by_novel(novel.id) or []

        prompt = self.__create_prompt(novel, characters)
        data = await self._generate(prompt, reasoning_effort=self._reasoning_effort)

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
                # MVP: новеллы линейные, развилок не генерируем
                target_choice=False,
                choice_stakes=None,
                scenes_count=item["scenes_count"],
            )
            step = await self._roadmap_service.add(step)
            roadmap.append(step)

        return roadmap

    def __create_prompt(self, novel: Novel, characters: list[Character]) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания истории и её тона создай роадмап сюжета — "
                "последовательность шагов, из которых складывается линейная история без развилок и выборов игрока. "
                "Количество шагов определи сам исходя из масштаба истории — обычно от 3 до 8. "
                "Для каждого шага укажи:\n"
                "1. title - короткое название шага.\n"
                "2. goal - что должно произойти в сюжете на этом шаге.\n"
                "3. scenes_count - сколько сцен потребуется, чтобы раскрыть этот шаг (обычно от 1 до 4).\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "roadmap": [
                    {
                      "title": string,
                      "goal": string,
                      "scenes_count": integer
                    }
                  ]
                }
                """
            ),
        }
        user_content = (
            f"Название: {novel.title}\n"
            f"Описание: {novel.description}\n"
            f"Тон повествования: {novel.tone}"
        )
        if characters:
            user_content += f"\nПерсонажи:\n{render_cast(characters)}"
            protagonist = find_protagonist(characters)
            if protagonist:
                user_content += (
                    f"\n\nГлавный герой: {protagonist.name} — протагонист, от чьего лица идёт история. "
                    f"Его арка: {protagonist.arc}. "
                    "Строй сюжет вокруг главного героя: его целей, решений, внутренних конфликтов и отношений."
                )
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]
