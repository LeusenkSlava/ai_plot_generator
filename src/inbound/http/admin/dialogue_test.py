"""In-process тест промпта диалога (без субпроцессов, без записи в БД, без аналитики).

Вьюха «Тест диалога» вызывает ``DialoguePromptTester`` напрямую — тот композирует
те же ``DialogueContextLoader`` / ``DialoguePromptBuilder`` / ``DeepSeekGenerator``,
что использует прод. Никаких subprocess-запусков и файловых логов больше нет.

DB-сессия открывается через ``async_session_factory()`` (не через FastAPI ``Depends``:
у SQLAdmin ``BaseView`` нет DI-цепочки). Вызов LLM — один ``await`` в обработчике,
таймаут задаёт ``settings.deepseek.TIMEOUT_S`` (уже встроен в ``build_deepseek_client``).
"""

from __future__ import annotations

import json

from sqladmin import BaseView, expose
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from src.core.novels.models import PromptVariant
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    PlayerChoiceService,
    RoadmapChoiceService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.context import DialogueContextLoader
from src.core.novels.services.generation.prompts.catalog import PromptCatalog
from src.core.novels.services.generation.prompts.dialogue import DialoguePromptBuilder
from src.core.novels.services.testing.dialogue_tester import DialoguePromptTester
from src.main.config.settings import settings
from src.outbound.ai.client import build_deepseek_client
from src.outbound.ai.deepseek_client import DeepSeekGenerator
from src.outbound.database.repositories.novel_repository import (
    CharacterRepository,
    DialogueLineRepository,
    NovelRepository,
    PlayerChoiceRepository,
    RoadmapChoiceRepository,
    RoadmapRepository,
    SceneRepository,
)
from src.outbound.database.repositories.prompt_repository import PromptRepository
from src.outbound.database.session import async_session_factory


class DialogueTestAdmin(BaseView):
    """Тест промпта диалога: render-only или полная генерация одной сцены."""

    name = "Тест диалога"
    icon = "fa-solid fa-flask"

    @expose("/test", methods=["GET"])
    async def index(self, request: Request):
        return await self.templates.TemplateResponse(
            request,
            "admin/dialogue_test.html",
            self._base_context(request),
        )

    @expose("/test", methods=["POST"])
    async def run(self, request: Request):
        context = self._base_context(request)
        form = await request.form()

        # Эхо полей формы, чтобы не терять введённое после POST.
        context.update(
            {
                "scene_id": (form.get("scene_id") or "").strip(),
                "variant": (form.get("variant") or "").strip(),
                "mock": (form.get("mock") or ""),
                "model": (form.get("model") or "").strip(),
                "temperature": (form.get("temperature") or "").strip(),
                "think": bool(form.get("think")),
                "render_only": bool(form.get("render_only")),
            }
        )

        scene_id_raw = context["scene_id"]
        if not scene_id_raw:
            context["error"] = "Укажите ID сцены."
            return await self._render(request, context)

        try:
            scene_id = int(scene_id_raw)
        except ValueError:
            context["error"] = "ID сцены должен быть целым числом."
            return await self._render(request, context)

        variant = context["variant"] or None
        if variant is not None and variant not in {v.value for v in PromptVariant}:
            context["error"] = f"Неизвестный вариант промптов: {variant!r}."
            return await self._render(request, context)

        mock = None
        mock_raw = (form.get("mock") or "").strip()
        if mock_raw:
            try:
                mock = json.loads(mock_raw)
            except json.JSONDecodeError as exc:
                context["error"] = f"Мок не является валидным JSON: {exc}"
                return await self._render(request, context)
            if not isinstance(mock, dict):
                context["error"] = (
                    "Мок должен быть JSON-объектом вида {system_template, user_template}."
                )
                return await self._render(request, context)

        model = context["model"] or settings.deepseek.MODEL
        temperature_raw = context["temperature"]
        try:
            temperature = (
                float(temperature_raw)
                if temperature_raw
                else settings.deepseek.DIALOGUE_TEMPERATURE
            )
        except ValueError:
            context["error"] = "temperature должна быть числом."
            return await self._render(request, context)

        think = context["think"]
        render_only = context["render_only"]

        try:
            result = await self._execute(
                scene_id,
                variant,
                mock,
                model=model,
                temperature=temperature,
                think=think,
                render_only=render_only,
            )
        except (
            Exception
        ) as exc:  # noqa: BLE001 — dev-инструмент, показываем ошибку как есть
            context["error"] = f"{type(exc).__name__}: {exc}"
            return await self._render(request, context)

        context["result"] = result
        return await self._render(request, context)

    # ------------------------------------------------------------------
    # Вспомогательное
    # ------------------------------------------------------------------

    def _base_context(self, request: Request) -> dict:
        return {
            "base_url": settings.admin.BASE_URL.rstrip("/"),
            "post_url": request.url_for("admin:view-run"),
            "variants": [("", "из новеллы (по умолчанию)")]
            + [(v.value, v.value) for v in PromptVariant],
            "model_default": settings.deepseek.MODEL,
            "temperature_default": settings.deepseek.DIALOGUE_TEMPERATURE,
            # Значения формы по умолчанию (на POST перезаписываются эхом).
            "scene_id": "",
            "variant": "",
            "mock": "",
            "model": "",
            "temperature": "",
            "think": settings.deepseek.DIALOGUE_THINK,
            "render_only": False,
            "error": None,
            "result": None,
        }

    async def _render(self, request: Request, context: dict):
        return await self.templates.TemplateResponse(
            request, "admin/dialogue_test.html", context
        )

    @staticmethod
    def _build_loader(session: AsyncSession) -> DialogueContextLoader:
        """Loader контекста сцены поверх одной сессии БД (как в проде)."""
        return DialogueContextLoader(
            novel_service=NovelService(NovelRepository(session)),
            scene_service=SceneService(SceneRepository(session)),
            roadmap_service=RoadmapService(RoadmapRepository(session)),
            character_service=CharacterService(CharacterRepository(session)),
            dialogue_line_service=DialogueLineService(DialogueLineRepository(session)),
            roadmap_choice_service=RoadmapChoiceService(
                RoadmapChoiceRepository(session)
            ),
            player_choice_service=PlayerChoiceService(PlayerChoiceRepository(session)),
            prompt_catalog=PromptCatalog(PromptRepository(session)),
        )

    @staticmethod
    async def _execute(
        scene_id: int,
        variant: str | None,
        mock: dict | None,
        *,
        model: str,
        temperature: float,
        think: bool,
        render_only: bool,
    ) -> dict:
        async with async_session_factory() as session:
            tester = DialoguePromptTester(
                loader=DialogueTestAdmin._build_loader(session),
                builder=DialoguePromptBuilder(),
                client=DeepSeekGenerator(
                    build_deepseek_client(),
                    log_call=lambda **kw: None,
                ),
            )
            if render_only:
                result = await tester.render(scene_id, variant=variant, mock=mock)
                return {
                    "scene_id": result.scene_id,
                    "scene_title": result.scene_title,
                    "variant": result.variant,
                    "version": result.version,
                    "messages": result.messages,
                    "lines": None,
                    "raw": None,
                }

            result = await tester.generate(
                scene_id,
                variant=variant,
                mock=mock,
                model=model,
                temperature=temperature,
                think=think,
            )
            return {
                "scene_id": result.render.scene_id,
                "scene_title": result.render.scene_title,
                "variant": result.render.variant,
                "version": result.render.version,
                "messages": result.render.messages,
                "lines": result.lines,
                "raw": json.dumps(result.raw, ensure_ascii=False, indent=2),
            }
