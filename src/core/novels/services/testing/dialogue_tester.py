"""Тест промпта диалога in-process (без субпроцессов, без записи в БД, без аналитики).

``DialoguePromptTester`` — единственное место, где «тестируем диалог». Он только
композирует уже готовые компоненты: читает контекст сцены через
``DialogueContextLoader``, рендерит промпт через ``DialoguePromptBuilder`` и,
опционально, вызывает LLM через ``DeepSeekGenerator``. Сам он промпт не строит и
в DeepSeek не ходит. В БД ничего не пишется; аналитика отключается тем, что клиент
создаётся с ``log_call=lambda **kw: None`` (см. админ-вьюху).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from src.core.novels.models import DEFAULT_PROMPT_VARIANT, Prompt, PromptKey
from src.core.novels.services.generation.context import DialogueContextLoader
from src.core.novels.services.generation.prompts.dialogue import DialoguePromptBuilder
from src.core.novels.services.testing.format import format_dialogue_lines


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Рендер промпта: сообщения ``[system, user]`` + мета."""

    messages: list[dict]
    variant: str
    version: int
    scene_id: int
    scene_title: str


@dataclass(frozen=True, slots=True)
class GenerateResult:
    """Генерация диалога: рендер + отформатированные реплики + сырой JSON ответа."""

    render: RenderResult
    lines: list[str]
    raw: dict


def apply_mock(template: Prompt, mock: dict) -> Prompt:
    """Переопределяет шаблон моком ``{system_template, user_template}`` локально.

    Мок не трогает БД — переопределяется только in-memory копия шаблона через
    ``dataclasses.replace``. Ключи, которых нет в моке, остаются из БД.
    """
    return replace(
        template,
        system_template=mock.get("system_template", template.system_template),
        user_template=mock.get("user_template", template.user_template),
    )


class DialoguePromptTester:
    """Композиция ``loader + builder + client`` для теста диалога сцены."""

    def __init__(
        self,
        loader: DialogueContextLoader,
        builder: DialoguePromptBuilder,
        client,
    ) -> None:
        self._loader = loader
        self._builder = builder
        self._client = client

    async def render(self, scene_id: int, variant: str | None = None, mock: dict | None = None) -> RenderResult:
        """Собирает промпт диалога сцены без вызова LLM и без записи в БД.

        ``variant=None`` — берётся из новеллы (``novel.prompt_variant``); мок
        переопределяет шаблон локально.
        """
        read = await self._loader.load(scene_id)
        variant = variant or str(
            read.novel.prompt_variant if read.novel else DEFAULT_PROMPT_VARIANT
        )
        template = await self._loader.prompt_catalog.get(PromptKey.DIALOGUE, variant)
        if mock:
            template = apply_mock(template, mock)
        ctx = await self._loader.load_context(scene_id, read=read)
        messages = self._builder.build(template, ctx)
        return RenderResult(
            messages=messages,
            variant=variant,
            version=template.version,
            scene_id=scene_id,
            scene_title=read.scene.title,
        )

    async def generate(
        self,
        scene_id: int,
        variant: str | None = None,
        mock: dict | None = None,
        *,
        model: str,
        temperature: float,
        think: bool,
    ) -> GenerateResult:
        """``render()`` + один вызов LLM + форматирование реплик."""
        render = await self.render(scene_id, variant=variant, mock=mock)
        data = await self._client.generate(
            render.messages,
            model=model,
            temperature=temperature,
            think=think,
        )
        return GenerateResult(
            render=render,
            lines=format_dialogue_lines(data),
            raw=data,
        )
