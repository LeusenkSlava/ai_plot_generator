import logging

from src.core.novels.exceptions import NovelGenerationError
from src.core.novels.interfaces import NovelGeneratorProtocol
from src.core.novels.models import Novel
from src.core.novels.services.crud import NovelService

logger = logging.getLogger(__name__)


class NovelGenerator:
    def __init__(self, novel_service: NovelService, generator: NovelGeneratorProtocol):
        self._novel_service = novel_service
        self._generator = generator

    async def generate(self, user_prompt: str) -> Novel:
        promt = await self.__create_promt(user_prompt)

        try:
            data = await self._generator.generate(promt)
        except Exception as e:
            logger.error(f"NovelGenerator.generate: {e}")
            raise NovelGenerationError(str(e))

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

    async def __create_promt(self, user_promt: str) -> list[str]:
        """Создает промт для созданеия новеллы на основе пользовательского промта"""
        system_promt = {
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
        user_promt = {"role": "user", "content": user_promt}
        return [system_promt, user_promt]
