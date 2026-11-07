import logging

from src.core.codex.models import Background, CodexCharacter, Universe
from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import (
    DEFAULT_PROMPT_VARIANT,
    Novel,
    NovelMode,
    Prompt,
    PromptKey,
)
from src.core.novels.services.crud import NovelService
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.prompts.catalog import (
    PromptCatalog,
    render_messages,
)
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
        *, prompt_catalog: PromptCatalog,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._codex_service = codex_service
        self._reasoning_effort = reasoning_effort
        self._prompts = prompt_catalog

    async def generate(
        self,
        user_prompt: str,
        universe_id: int | None = None,
        mode: NovelMode = NovelMode.LINEAR,
        prompt_variant: str = DEFAULT_PROMPT_VARIANT,
        author_id: int | None = None,
        *,
        step: TransactionFactory = noop_step,
    ) -> Novel:
        # Read-фаза: шаблон промпта из БД (короткая транзакция, до LLM).
        async with step():
            template = await self._prompts.get(PromptKey.NOVEL, prompt_variant)

        # Codex (HTTP) и LLM — вне транзакции: соединение Postgres здесь не держим.
        codex_context = None
        if universe_id:
            universe, characters, backgrounds = await self.__load_universe(universe_id)
            codex_context = render_all(universe, characters, backgrounds)

        prompt = self.__create_prompt(template, user_prompt, codex_context)
        data = await self._generate(prompt, reasoning_effort=self._reasoning_effort)

        novel = Novel.from_llm(
            data,
            universe_id=universe_id,
            author_id=author_id,
            mode=mode,
            prompt_variant=prompt_variant,
        )
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

    @staticmethod
    def __create_prompt(
        template: Prompt, user_prompt: str, codex_context: str | None
    ) -> list[dict]:
        """Рендерит шаблон (чистая функция — БД уже прочитана в read-фазе)."""
        codex_block = ""
        if codex_context:
            codex_block = (
                "\nThe story takes place in an existing universe from the knowledge base. "
                "Use ONLY these characters and locations, do not invent anything:\n"
                + codex_context
            )
        return render_messages(
            template,
            system_vars={
                "json_instruction": Novel.llm_json_instruction(),
                "codex_block": codex_block,
                "russian_note": RUSSIAN_OUTPUT_NOTE,
            },
            user_vars={"user_prompt": user_prompt},
        )
