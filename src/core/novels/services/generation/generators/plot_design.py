"""Шаг design-doc: форма истории, нити и их бюджет — до роадмапа.

Один дешёвый вызов LLM (``think=False``, маленький JSON); роадмап потребляет
форму, бюджет нитей и сквозную линию как ограничения.
"""

import logging
from dataclasses import asdict

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import (
    Character,
    Novel,
    PlotDesign,
    PlotThread,
    Prompt,
    PromptKey,
)
from src.core.novels.services.crud import CharacterService, NovelService
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.prompts.cast import render_characters_block
from src.core.novels.services.generation.prompts.catalog import (
    PromptCatalog,
    render_messages,
)
from src.core.novels.services.generation.prompts.shapes import (
    DEFAULT_SHAPE,
    STORY_SHAPES,
    render_shape_catalog,
)
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE
from src.core.novels.services.generation.transactions import (
    TransactionFactory,
    noop_step,
)

logger = logging.getLogger(__name__)

# Отклик design-doc маленький и почти всегда валиден, поэтому ретраев меньше,
# чем у сцены/диалога: один повтор на сбой парсинга.
_PARSE_ATTEMPTS = 2


def _text(value) -> str:
    """Строка из ответа LLM без побочных пробелов; не строка — пустая строка."""
    return value.strip() if isinstance(value, str) else ""


def _string_list(value) -> list[str]:
    """Список непустых строк из ответа LLM (пустые элементы отбрасываются)."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item)
        if text:
            result.append(text)
    return result


def _int_or(value, default: int) -> int:
    """Целое из ответа LLM; нечисло/None — значение по умолчанию."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_shape(value) -> str:
    """Slug формы из библиотеки; невалидный или пустой — форма по умолчанию."""
    slug = _text(value).lower()
    return slug if slug in STORY_SHAPES else DEFAULT_SHAPE


def _parse_threads(raw, character_names: set[str]) -> list[PlotThread]:
    """Нити с бюджетом шагов; имена персонажей сужаются до каста."""
    if not isinstance(raw, list):
        return []
    # Ключ без регистра, значение — каноническое имя из каста (уходит в промпт).
    canonical = {name.strip().casefold(): name for name in character_names}

    threads: list[PlotThread] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if not name:
            continue
        min_steps = max(1, _int_or(item.get("min_steps"), 1))
        max_steps = max(min_steps + 1, _int_or(item.get("max_steps"), min_steps + 1))

        characters = []
        for raw_name in _string_list(item.get("characters")):
            cast_name = canonical.get(raw_name.casefold())
            if cast_name is None:
                logger.warning(
                    "plot_design referenced unknown character '%s', dropped", raw_name
                )
                continue
            if cast_name not in characters:
                characters.append(cast_name)

        threads.append(
            PlotThread(
                name=name,
                characters=characters,
                min_steps=min_steps,
                max_steps=max_steps,
            )
        )
    return threads


def parse_design(data: dict, character_names: set[str]) -> PlotDesign:
    """Валидирует ответ LLM и собирает :class:`PlotDesign`.

    Неизвестные имена персонажей отбрасываются, отсутствие нитей — ошибка.
    """
    if not isinstance(data, dict):
        raise GenerationError("plot_design returned no JSON object")

    threads = _parse_threads(data.get("threads"), character_names)
    if not threads:
        raise GenerationError("plot_design returned no threads")

    return PlotDesign(
        shape=_parse_shape(data.get("shape")),
        genres=_string_list(data.get("genres")),
        through_line=_text(data.get("through_line")),
        threads=threads,
        tropes=_string_list(data.get("tropes")),
        pivot=_text(data.get("pivot")),
        tone_curve=_string_list(data.get("tone_curve")),
    )


class PlotDesignGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        character_service: CharacterService,
        generator: GeneratorProtocol,
        reasoning_effort: str | None = None,
        think: bool = False,
        *, prompt_catalog: PromptCatalog,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._character_service = character_service
        self._reasoning_effort = reasoning_effort
        self._think = think
        self._prompts = prompt_catalog

    async def generate(
        self,
        novel_id: int,
        *,
        user_prompt: str,
        step: TransactionFactory = noop_step,
    ) -> PlotDesign:
        # 1) Read-фаза: короткая транзакция, до вызова LLM.
        async with step():
            novel = await self._novel_service.get(novel_id)
            if not novel:
                raise GenerationError(f"Novel with id {novel_id} not found")
            characters = await self._character_service.list_by_novel(novel.id) or []
            template = await self._prompts.get(
                PromptKey.PLOT_DESIGN, novel.prompt_variant
            )

        # 2) LLM-фаза: без транзакции.
        prompt = self.__create_prompt(template, novel, characters, user_prompt)
        design = await self.__generate_design(prompt, characters)

        # 3) Write-фаза: снапшот design-doc для отладки и будущего переиспользования.
        async with step():
            await self._novel_service.update_plot_design(novel.id, asdict(design))

        return design

    async def __generate_design(
        self, prompt: list[dict], characters: list[Character]
    ) -> PlotDesign:
        """Вызов LLM и валидация; плохой ответ один раз перезапрашивается."""
        character_names = {c.name for c in characters}
        for attempt in range(1, _PARSE_ATTEMPTS + 1):
            data = await self._generate(
                prompt, think=self._think, reasoning_effort=self._reasoning_effort
            )
            try:
                return parse_design(data, character_names)
            except GenerationError as e:
                if attempt == _PARSE_ATTEMPTS:
                    raise
                logger.warning("plot_design response rejected (%s), retrying once", e)
        raise GenerationError("plot_design returned no design")  # pragma: no cover

    @staticmethod
    def __create_prompt(
        template: Prompt,
        novel: Novel,
        characters: list[Character],
        user_prompt: str,
    ) -> list[dict]:
        return render_messages(
            template,
            system_vars={
                "shape_catalog": render_shape_catalog(),
                "russian_note": RUSSIAN_OUTPUT_NOTE,
            },
            user_vars={
                "title": novel.title,
                "description": novel.description,
                "tone": novel.tone,
                "characters_block": render_characters_block(characters),
                "user_prompt": user_prompt,
            },
        )
