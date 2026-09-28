import logging

from src.core.novels.interfaces import GeneratorProtocol
from src.core.novels.models import Novel
from src.core.novels.services.crud import NovelService
from src.core.novels.services.generate.base import BaseGenerator

logger = logging.getLogger(__name__)


class NovelGenerator(BaseGenerator):
    def __init__(self, novel_service: NovelService, generator: GeneratorProtocol):
        super().__init__(generator)
        self._novel_service = novel_service

    async def generate(self, user_prompt: str) -> Novel:
        prompt = self.__create_prompt(user_prompt)
        data = await self._generate(prompt)

        novel = Novel(
            id=None,
            title=data["title"],
            public_description=data["public_description"],
            description=data["description"],
            tone=data["tone"],
            created_at=None,
            updated_at=None,
        )
        novel = await self._novel_service.add(novel)
        return novel

    def __create_prompt(self, user_prompt: str) -> list[dict]:
        """Создает промт для создания новеллы на основе пользовательского промта"""
        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл."
                "По тегам и описанию от пользователя создай творческую основу истории для дальнейшей генерации."
                "Создай:"
                "1. title - короткое, цепляющее название."
                "2. public_description - Описание для пользователя, БЕЗ спойлеров."
                "3. description - Галвное описание истории по нему будет генерировться сюжет."
                "5. tone - Тон и стиль повествования."
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме"
                """
                {
                  "title": string,
                  "public_description": string,
                  "description": string,
                  "tone": string,
                }
                """
            ),
        }
        user_prompt = {"role": "user", "content": user_prompt}
        return [system_prompt, user_prompt]
