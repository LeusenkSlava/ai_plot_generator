import logging

from src.core.codex.models import Background, CodexCharacter, Universe
from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Novel
from src.core.novels.services.crud import NovelService
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.prompts.context import render_all
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE
from src.core.novels.services.generation.transactions import (
    TransactionFactory,
    noop_step,
)

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

    async def generate(
        self,
        user_prompt: str,
        universe_id: int | None = None,
        *,
        step: TransactionFactory = noop_step,
    ) -> Novel:
        # Codex (HTTP) и LLM — вне транзакции: соединение Postgres здесь не держим.
        codex_context = None
        if universe_id:
            universe, characters, backgrounds = await self.__load_universe(universe_id)
            codex_context = render_all(universe, characters, backgrounds)

        prompt = self.__create_prompt(user_prompt, codex_context)
        data = await self._generate(prompt, reasoning_effort=self._reasoning_effort)

        novel = Novel.from_llm(data, universe_id=universe_id)
        # Запись — единственная DB-операция генератора: короткая транзакция.
        async with step():
            novel = await self._novel_service.add(novel)
        return novel

    async def __load_universe(
        self, universe_id: int
    ) -> tuple[Universe, list[CodexCharacter], list[Background]]:
        try:
            universe = await self._codex_service.get_universe(universe_id)
            characters = await self._codex_service.get_characters(universe_id)
            backgrounds = await self._codex_service.get_backgrounds(universe_id)
        except Exception as e:
            raise GenerationError(f"Codex request failed: {e}") from e
        if universe is None:
            raise GenerationError(f"Universe with id {universe_id} not found in Codex")
        return universe, characters, backgrounds

    def __create_prompt(
        self, user_prompt: str, codex_context: str | None = None
    ) -> list[dict]:
        """Создает промт для создания новеллы на основе пользовательского промта."""
        system_content = (
            "You are a screenwriter for interactive visual novels. "
            "Based on the user's tags and description, create the creative foundation "
            "of the story for further generation. " + Novel.llm_json_instruction()
        )
        if codex_context:
            system_content += (
                "\nThe story takes place in an existing universe from the knowledge base. "
                "Use ONLY these characters and locations, do not invent anything:\n"
                + codex_context
            )
        system_content += f"\n{RUSSIAN_OUTPUT_NOTE}"

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_prompt},
        ]
