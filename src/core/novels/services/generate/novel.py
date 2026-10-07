import logging

from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Novel
from src.core.novels.services.crud import NovelService
from src.core.novels.services.generate.base import BaseGenerator

logger = logging.getLogger(__name__)


class NovelGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        codex_service: CodexService,
        generator: GeneratorProtocol,
        reasoning_effort: str | None = None,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._codex_service = codex_service
        self._reasoning_effort = reasoning_effort

    async def generate(self, user_prompt: str, universe_id: int | None = None) -> Novel:
        codex_context = None
        if universe_id:
            codex_context = await self.__codex_context(universe_id)

        prompt = self.__create_prompt(user_prompt, codex_context)
        data = await self._generate(prompt, reasoning_effort=self._reasoning_effort)

        novel = Novel.from_llm(data, universe_id=universe_id)
        novel = await self._novel_service.add(novel)
        return novel

    async def __codex_context(self, universe_id: int) -> str:
        """Вселенная, персонажи и фоны из Codex"""
        try:
            universe = await self._codex_service.get_universe(universe_id)
            characters = await self._codex_service.get_characters(universe_id)
            backgrounds = await self._codex_service.get_backgrounds(universe_id)
        except Exception as e:
            raise GenerationError(f"Codex request failed: {e}") from e

        if universe is None:
            raise GenerationError(f"Universe with id {universe_id} not found in Codex")

        parts = [f"Вселенная: {universe.title}\n{universe.description}"]
        if characters:
            parts.append(
                "Персонажи (других нет):\n"
                + "\n".join(f"- {c.name}: {c.description}" for c in characters)
            )
        if backgrounds:
            parts.append(
                "Локации (других нет):\n"
                + "\n".join(f"- {b.description}" for b in backgrounds)
            )
        return "\n\n".join(parts)

    def __create_prompt(
        self, user_prompt: str, codex_context: str | None = None
    ) -> list[dict]:
        """Создает промт для создания новеллы на основе пользовательского промта."""
        system_content = (
            "Ты сценарист интерактивных визуальных новелл. "
            "По тегам и описанию от пользователя создай творческую основу истории "
            "для дальнейшей генерации. " + Novel.llm_json_instruction()
        )
        if codex_context:
            system_content += (
                "\nИстория происходит в существующей вселенной из базы знаний. "
                "Используй ТОЛЬКО этих персонажей и локации, ничего не выдумывай:\n"
                + codex_context
            )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_prompt},
        ]
