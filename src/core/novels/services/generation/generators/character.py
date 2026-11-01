import logging

from src.core.codex.models import CodexCharacter
from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Character, Novel, Prompt, PromptKey
from src.core.novels.services.crud import CharacterService, NovelService
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.prompts.catalog import (
    PromptCatalog,
    render_messages,
)
from src.core.novels.services.generation.prompts.context import render_character_catalog
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE
from src.core.novels.services.generation.transactions import (
    TransactionFactory,
    noop_step,
)

logger = logging.getLogger(__name__)


class CharacterGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        character_service: CharacterService,
        codex_service: CodexService,
        generator: GeneratorProtocol,
        reasoning_effort: str | None = None,
        think: bool = True,
        *, prompt_catalog: PromptCatalog,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._character_service = character_service
        self._codex_service = codex_service
        self._reasoning_effort = reasoning_effort
        self._think = think
        self._prompts = prompt_catalog

    async def generate(
        self,
        novel_id: int,
        *,
        step: TransactionFactory = noop_step,
    ) -> list[Character]:
        # 1) Read-фаза: короткая транзакция, соединение возвращается в пул до LLM.
        async with step():
            novel = await self._novel_service.get(novel_id)
            if not novel:
                raise GenerationError(f"Novel with id {novel_id} not found")
            template = await self._prompts.get(PromptKey.CHARACTER, novel.prompt_variant)

        # 2) LLM-фаза: Codex (HTTP) и генерация — без транзакции.
        codex_characters: list[CodexCharacter] = []
        if novel.universe_id is not None:
            try:
                codex_characters = await self._codex_service.get_characters(
                    novel.universe_id
                )
            except Exception as e:
                raise GenerationError(f"Codex characters request failed: {e}") from e
        codex_by_slug = {c.slug: c for c in codex_characters}

        prompt = self.__create_prompt(template, novel, codex_characters)
        data = await self._generate(
            prompt, think=self._think, reasoning_effort=self._reasoning_effort
        )

        characters_data = data.get("characters")
        if not characters_data:
            raise GenerationError("Generator returned no characters")

        characters = []
        for item in characters_data:
            codex_character = codex_by_slug.get(item.get("codex_slug") or "")
            if codex_by_slug and item.get("codex_slug") and not codex_character:
                logger.warning(
                    f"Generator referenced unknown codex character '{item['codex_slug']}'"
                )
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
                gender=codex_character.gender if codex_character else None,
                is_protagonist=bool(item.get("is_protagonist", False)),
            )
            characters.append(character)

        self.__ensure_single_protagonist(characters)

        # 3) Write-фаза: короткая транзакция только на запись.
        saved = []
        async with step():
            for character in characters:
                character = await self._character_service.add(character)
                saved.append(character)

        return saved

    @staticmethod
    def __ensure_single_protagonist(characters: list[Character]) -> None:
        """Инвариант: главный герой ровно один.

        Если LLM вернул несколько — оставляем первого и сбрасываем остальных;
        если ни одного — назначаем первого персонажа.
        """
        protagonists = [c for c in characters if c.is_protagonist]
        if len(protagonists) == 1:
            return
        if protagonists:
            for c in protagonists[1:]:
                c.is_protagonist = False
            return
        if characters:
            characters[0].is_protagonist = True

    @staticmethod
    def __create_prompt(
        template: Prompt, novel: Novel, codex_characters: list[CodexCharacter]
    ) -> list[dict]:
        codex_block = ""
        codex_catalog = ""
        if codex_characters:
            codex_block = (
                "\nThe story takes place in an existing universe. Take characters ONLY from the knowledge base below: "
                "convey their name, personality, and manner of speech exactly per their description; do not invent anything. "
                "For each character add the field codex_slug - the character's slug from the knowledge base, exactly as in the list.\n"
                "Determine the protagonist from the story description, not from the knowledge base: if the story's protagonist is "
                "a different person who takes the place of this universe's protagonist, make them the protagonist "
                "(is_protagonist=true, do not set codex_slug). In the other characters' traits, wherever the previous "
                "protagonist is mentioned, replace their name with the new protagonist's name while keeping the facts — "
                "including who the character lives with (for example, «живёт в домике с Семёном» → «живёт в домике с Кахевником»)."
            )
            codex_catalog = (
                "\nCharacters from the knowledge base:\n"
                + render_character_catalog(codex_characters)
            )
        return render_messages(
            template,
            system_vars={"codex_block": codex_block, "russian_note": RUSSIAN_OUTPUT_NOTE},
            user_vars={
                "title": novel.title,
                "description": novel.description,
                "tone": novel.tone,
                "codex_catalog": codex_catalog,
            },
        )
