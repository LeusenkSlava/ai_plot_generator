import logging

from src.core.codex.models import CodexCharacter
from src.core.codex.services import CodexService

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
        codex_service: CodexService,
        generator: GeneratorProtocol,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._character_service = character_service
        self._codex_service = codex_service

    async def generate(self, novel_id: int) -> list[Character]:
        novel = await self._novel_service.get(novel_id)
        if not novel:
            raise GenerationError(f"Novel with id {novel_id} not found")

        # Без вселенной в Codex не ходим
        codex_characters: list[CodexCharacter] = []
        if novel.universe_id is not None:
            try:
                codex_characters = await self._codex_service.get_characters(novel.universe_id)
            except Exception as e:
                raise GenerationError(f"Codex characters request failed: {e}") from e
        codex_by_slug = {c.slug: c for c in codex_characters}

        prompt = self.__create_prompt(novel, codex_characters)
        data = await self._generate(prompt)

        characters_data = data.get("characters")
        if not characters_data:
            raise GenerationError("Generator returned no characters")

        characters = []
        for item in characters_data:
            codex_character = codex_by_slug.get(item.get("codex_slug") or "")
            if codex_by_slug and item.get("codex_slug") and not codex_character:
                logger.warning(f"Generator referenced unknown codex character '{item['codex_slug']}'")
            character = Character(
                id=None,
                created_at=None,
                updated_at=None,
                novel_id=novel.id,
                name=item["name"],
                role=item["role"],
                arc=item["arc"],
                voice_notes=item["voice_notes"],
                codex_character_id=codex_character.id if codex_character else None,
            )
            character = await self._character_service.add(character)
            characters.append(character)

        return characters

    def __create_prompt(
        self, novel: Novel, codex_characters: list[CodexCharacter]
    ) -> list[dict]:
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
        user_content = (
            f"Название: {novel.title}\n"
            f"Описание: {novel.description}\n"
            f"Тон повествования: {novel.tone}"
        )
        if codex_characters:
            system_prompt["content"] += (
                "\nИстория происходит в существующей вселенной. Бери персонажей ТОЛЬКО из базы знаний ниже: "
                "имя, характер и манеру речи передавай точно по их описанию, ничего не выдумывай. "
                "Для каждого персонажа добавь поле codex_slug - slug персонажа из базы знаний, точно как в списке."
            )
            catalog = "\n".join(
                f"- slug: {c.slug}; имя: {c.name}; описание: {c.description}"
                + (f"; манера речи: {c.speech_style}" if c.speech_style else "")
                + (f"; теги: {', '.join(t.name for t in c.tags)}" if c.tags else "")
                for c in codex_characters
            )
            user_content += f"\nПерсонажи из базы знаний:\n{catalog}"
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]
