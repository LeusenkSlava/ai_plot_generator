import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces import GeneratorProtocol
from src.core.novels.models import Character, Novel
from src.core.novels.services.crud import CharacterService, NovelService
from src.core.novels.services.generate.base import BaseGenerator

logger = logging.getLogger(__name__)


class CharacterGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        character_service: CharacterService,
        generator: GeneratorProtocol,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._character_service = character_service

    async def generate(self, novel_id: int) -> list[Character]:
        novel = await self._novel_service.get(novel_id)
        if not novel:
            raise GenerationError(f"Novel with id {novel_id} not found")

        prompt = self.__create_prompt(novel)
        data = await self._generate(prompt)

        characters_data = data.get("characters")
        if not characters_data:
            raise GenerationError("Generator returned no characters")

        characters = []
        for item in characters_data:
            character = Character(
                id=None,
                created_at=None,
                updated_at=None,
                novel_id=novel.id,
                name=item["name"],
                role=item["role"],
                arc=item["arc"],
                voice_notes=item["voice_notes"],
            )
            character = await self._character_service.add(character)
            characters.append(character)

        return characters

    def __create_prompt(self, novel: Novel) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания истории и её тона создай набор персонажей для сюжета. "
                "Количество персонажей определи сам исходя из масштаба истории — обычно от 2 до 6. "
                "Обязательно включи главного героя/героиню и хотя бы одного антагониста или значимого второстепенного персонажа. "
                "Для каждого персонажа укажи:\n"
                "1. name - имя персонажа.\n"
                "2. role - роль в истории (протагонист, антагонист, союзник, love interest и т.д.).\n"
                "3. arc - краткое описание сюжетной арки персонажа.\n"
                "4. voice_notes - заметки о манере речи и характере, которые помогут в дальнейшем генерировать диалоги.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "characters": [
                    {
                      "name": string,
                      "role": string,
                      "arc": string,
                      "voice_notes": string
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
