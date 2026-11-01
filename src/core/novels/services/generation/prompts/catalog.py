"""Каталог промптов: резолв версии по (key, variant) и рендер в сообщения LLM.

Источник шаблонов — только БД (``PromptRepositoryProtocol``): активная версия
всегда должна быть в таблице ``prompts`` (её кладут туда миграции). Если
активной версии нет — это ошибка данных, а не повод молча подставить
встроенный текст: каталог бросает ``PromptNotFoundError``. Встроенного
fallback-текста в коде нет — промпты живут только в БД.

Fetch и render разделены намеренно: ``get`` — асинхронное чтение из БД (его
генераторы вызывают внутри короткой read-транзакции ``step()``), а
``render_messages`` — чистая функция без БД, которую можно звать в LLM-фазе,
не держа соединение и не открывая транзакцию.
"""

from src.core.novels.exceptions import PromptNotFoundError
from src.core.novels.interfaces.repository import PromptRepositoryProtocol
from src.core.novels.models import DEFAULT_PROMPT_VARIANT, Prompt
from src.core.novels.services.generation.prompts.render import render_template


def render_messages(
    prompt: Prompt,
    *,
    system_vars: dict[str, object] | None = None,
    user_vars: dict[str, object] | None = None,
) -> list[dict]:
    """Рендерит шаблон в ``[system, user]`` (чистая функция, без БД).

    ``user``-сообщение добавляется, только если шаблон непуст. Все плейсхолдеры
    обязательны — отсутствующая переменная даёт ``MissingPromptVariableError``.
    """
    messages = [
        {
            "role": "system",
            "content": render_template(prompt.system_template, **(system_vars or {})),
        }
    ]
    if prompt.user_template:
        messages.append(
            {
                "role": "user",
                "content": render_template(prompt.user_template, **(user_vars or {})),
            }
        )
    return messages


class PromptCatalog:
    """Резолвит активную версию шаблона по (key, variant) из БД."""

    def __init__(self, repository: PromptRepositoryProtocol):
        self._repository = repository

    async def get(self, key: str, variant: str = DEFAULT_PROMPT_VARIANT) -> Prompt:
        """Активная версия шаблона из БД; отсутствие версии — ошибка."""
        prompt = await self._repository.get_active(key, variant)
        if prompt is None:
            raise PromptNotFoundError(key, variant)
        return prompt
