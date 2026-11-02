#!/usr/bin/env python3
"""Перегенерация диалога сцены: промпт из БД + локальный мок. Без записи в БД.

Промпт диалога (``key="dialogue"``) загружается из таблицы ``prompts`` — активная
версия для нужного варианта. Контекст сцены (персонажи, предыдущая сцена,
последние реплики, изложение истории) восстанавливается из БД тем же кодом, что
и в проде (``DialogueContextLoader``), шаблон рендерится тем же
``DialoguePromptBuilder``, и отправляется в DeepSeek через тот же
``DeepSeekGenerator`` — но с отключённой аналитикой (``log_call=lambda **kw: None``).
Результат печатается в консоль; **в базу ничего не пишется**.

Мок — это локальный JSON с ключами ``system_template`` / ``user_template``.
Он переопределяет шаблон из БД для экспериментов, не трогая саму БД. По умолчанию
ищется ``scripts/mocks/dialogue.json``; путь можно задать через ``--mock``, а
``--no-mock`` отключает подгрузку. Сгенерировать мок из текущего шаблона БД:
``--export-mock scripts/mocks/dialogue.json``.

Режимы:
    # 1. По сцене из БД (вариант промптов берётся из новеллы)
    python scripts/regen_dialogue.py --scene-id 91
    python scripts/regen_dialogue.py --scene-id 91 --variant nsfw_high
    python scripts/regen_dialogue.py --scene-id 91 --mock scripts/mocks/dialogue.json
    python scripts/regen_dialogue.py --scene-id 91 --render-only   # только показать промпт

    # 2. Совместимость: дамп llm_prompts_*.md с уже сгенерированными сообщениями
    python scripts/regen_dialogue.py --dump llm_prompts_91.md --scene 820_1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path

# Скрипт лежит в scripts/ — добавляем корень проекта в sys.path, чтобы работали
# импорты src.* (как при запуске из админки, так и напрямую).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from src.core.novels.models import (  # noqa: E402
    Prompt,
    PromptKey,
    PromptVariant,
)
from src.core.novels.services.crud import (  # noqa: E402
    CharacterService,
    DialogueLineService,
    NovelService,
    PlayerChoiceService,
    RoadmapChoiceService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.context import DialogueContextLoader  # noqa: E402
from src.core.novels.services.generation.prompts.catalog import PromptCatalog  # noqa: E402
from src.core.novels.services.generation.prompts.dialogue import (  # noqa: E402
    DialoguePromptBuilder,
)
from src.core.novels.services.testing.format import format_dialogue_lines  # noqa: E402
from src.main.config.settings import settings  # noqa: E402
from src.outbound.ai.client import build_deepseek_client  # noqa: E402
from src.outbound.ai.deepseek_client import DeepSeekGenerator  # noqa: E402
from src.outbound.database.repositories.novel_repository import (  # noqa: E402
    CharacterRepository,
    DialogueLineRepository,
    NovelRepository,
    PlayerChoiceRepository,
    RoadmapChoiceRepository,
    RoadmapRepository,
    SceneRepository,
)
from src.outbound.database.repositories.prompt_repository import PromptRepository  # noqa: E402
from src.outbound.database.session import async_session_factory  # noqa: E402

DEFAULT_MOCK = PROJECT_ROOT / "scripts" / "mocks" / "dialogue.json"

_HEADER_RE = re.compile(r"^## (.+)$")
_META_RE = re.compile(r"^_scene_order=(\S+) · ts: (.+)_$")
_FENCE_RE = re.compile(r"```json\n(.*?)\n```", re.S)


def _build_loader(session: AsyncSession) -> DialogueContextLoader:
    """Loader контекста сцены поверх одной сессии БД (как в проде)."""
    return DialogueContextLoader(
        novel_service=NovelService(NovelRepository(session)),
        scene_service=SceneService(SceneRepository(session)),
        roadmap_service=RoadmapService(RoadmapRepository(session)),
        character_service=CharacterService(CharacterRepository(session)),
        dialogue_line_service=DialogueLineService(DialogueLineRepository(session)),
        roadmap_choice_service=RoadmapChoiceService(RoadmapChoiceRepository(session)),
        player_choice_service=PlayerChoiceService(PlayerChoiceRepository(session)),
        prompt_catalog=PromptCatalog(PromptRepository(session)),
    )


def _build_client(args: argparse.Namespace) -> DeepSeekGenerator:
    """Тот же клиент, что и в проде, но без аналитики/трассировки."""
    return DeepSeekGenerator(
        build_deepseek_client(),
        model=args.model,
        temperature=args.temperature,
        log_call=lambda **kw: None,
    )


async def load_template(variant: str, mock: dict | None) -> Prompt:
    """Активный шаблон диалога из БД; мок переопределяет шаблоны локально."""
    async with async_session_factory() as session:
        prompt = await PromptRepository(session).get_active(PromptKey.DIALOGUE, variant)
    if prompt is None:
        raise RuntimeError(
            f"В БД нет активного промпта key='{PromptKey.DIALOGUE}' variant='{variant}'. "
            "Заполните таблицу prompts (например, через админку)."
        )
    if mock:
        prompt = replace(
            prompt,
            system_template=mock.get("system_template", prompt.system_template),
            user_template=mock.get("user_template", prompt.user_template),
        )
    return prompt


# ---------------------------------------------------------------------------
# Режим 2: совместимость со старым дампом llm_prompts_*.md
# ---------------------------------------------------------------------------
def parse_records(text: str) -> list[dict]:
    records: list[dict] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        blocks = _FENCE_RE.findall(current["body"])
        messages = None
        if blocks:
            try:
                messages = json.loads(blocks[0])
            except json.JSONDecodeError:
                messages = None
        records.append(
            {
                "operation": current["operation"],
                "generator": current["generator"],
                "scene_order": current.get("scene_order"),
                "messages": messages or [],
            }
        )
        current = None

    for line in text.split("\n"):
        m = _HEADER_RE.match(line)
        if m:
            flush()
            operation, sep, generator = m.group(1).rpartition(" · ")
            current = {
                "operation": operation,
                "generator": generator if sep else "",
                "body": "",
                "scene_order": None,
            }
            continue
        if current is None:
            continue
        meta = _META_RE.match(line)
        if meta:
            current["scene_order"] = meta.group(1)
        current["body"] += line + "\n"
    flush()
    return records


def scene_key(operation: str) -> str:
    return operation[len("scene_"):] if operation.startswith("scene_") else operation


def _normalize_scene_key(value: str) -> str:
    """Ключ сцены без префикса ``scene_`` и символов ``_``.

    Так ``820_1``, ``scene_820_1`` и ``8201`` считаются одной сценой.
    """
    return scene_key(value).replace("_", "")


def find_dialogue(records: list[dict], scene_id: str) -> dict | None:
    key = _normalize_scene_key(scene_id)
    for rec in records:
        if rec["generator"] != "DialogueGenerator":
            continue
        if _normalize_scene_key(rec["operation"]) == key or _normalize_scene_key(
            rec["scene_order"] or ""
        ) == key:
            return rec
    return None


async def _run_dump(args) -> int:
    with open(args.dump, encoding="utf-8") as fh:
        records = parse_records(fh.read())

    rec = find_dialogue(records, args.scene)
    if rec is None:
        scenes = sorted({scene_key(r["operation"]) for r in records
                         if r["generator"] == "DialogueGenerator"})
        print(f"Ошибка: диалог для сцены '{args.scene}' не найден.", file=sys.stderr)
        print("Доступные сцены с диалогами:", ", ".join(scenes), file=sys.stderr)
        return 1

    print(f"# {rec['operation']} · {rec['generator']}  model={args.model}", file=sys.stderr)
    if args.render_only:
        for m in rec["messages"]:
            print(f"\n=== {m.get('role')} ===\n{m.get('content')}")
        return 0

    client = _build_client(args)
    data = await client.generate(
        rec["messages"],
        think=args.think,
        reasoning_effort=args.reasoning_effort or None,
    )

    result = "\n".join(format_dialogue_lines(data))
    print(result)
    if args.out:
        Path(args.out).write_text(result + "\n", encoding="utf-8")
        print(f"\nСохранено: {args.out}", file=sys.stderr)
    return 0


async def _run_db(args) -> int:
    if args.export_mock:
        variant = args.variant or PromptVariant.DEFAULT.value
        template = await load_template(variant, mock=None)
        payload = {
            "variant": variant,
            "system_template": template.system_template,
            "user_template": template.user_template,
        }
        out = Path(args.export_mock)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Мок выгружен: {out}", file=sys.stderr)
        return 0

    mock_path = None if args.no_mock else (args.mock or DEFAULT_MOCK)
    mock = None
    if mock_path and os.path.isfile(mock_path):
        with open(mock_path, encoding="utf-8") as fh:
            mock = json.load(fh)
        print(f"# мок: {mock_path}", file=sys.stderr)

    async with async_session_factory() as session:
        loader = _build_loader(session)
        read = await loader.load(args.scene_id)

        variant = args.variant or str(read.novel.prompt_variant)
        template = await load_template(variant, mock)

        ctx = await loader.load_context(args.scene_id, read=read)

    builder = DialoguePromptBuilder()
    messages = builder.build(template, ctx)

    print(
        f"# scene={args.scene_id} key=dialogue variant={variant} "
        f"version={template.version} model={args.model}",
        file=sys.stderr,
    )

    if args.render_only:
        for m in messages:
            print(f"\n=== {m.get('role')} ===\n{m.get('content')}")
        return 0

    client = _build_client(args)
    data = await client.generate(
        messages,
        think=args.think,
        reasoning_effort=args.reasoning_effort or None,
    )

    result = "\n".join(format_dialogue_lines(data))
    print(result)
    if args.out:
        Path(args.out).write_text(result + "\n", encoding="utf-8")
        print(f"\nСохранено: {args.out}", file=sys.stderr)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Перегенерация диалога сцены: промпт из БД + мок, без записи в БД.",
    )
    parser.add_argument("--scene-id", type=int, default=None, help="ID сцены в БД")
    parser.add_argument(
        "--variant",
        choices=[v.value for v in PromptVariant],
        default=None,
        help="Вариант промптов (по умолчанию берётся из новеллы)",
    )
    parser.add_argument(
        "--mock",
        default=None,
        help=f"JSON-мок, переопределяющий шаблон (по умолчанию {DEFAULT_MOCK})",
    )
    parser.add_argument("--no-mock", action="store_true", help="Не подгружать мок")
    parser.add_argument(
        "--export-mock",
        default=None,
        help="Выгрузить шаблон диалога из БД в JSON-мок и выйти",
    )
    parser.add_argument("--dump", default=None, help="Дамп llm_prompts_*.md (режим совместимости)")
    parser.add_argument("--scene", default=None, help="Ключ сцены в дампе (для --dump)")
    parser.add_argument("--render-only", action="store_true", help="Только показать промпт, не вызывать LLM")
    parser.add_argument("--out", default=None, help="Сохранить результат в файл")
    parser.add_argument("--model", default=settings.deepseek.MODEL, help="Модель DeepSeek")
    parser.add_argument("--temperature", type=float, default=settings.deepseek.DIALOGUE_TEMPERATURE, help="Температура")
    parser.add_argument("--no-think", action="store_true", help="Отключить thinking-режим")
    parser.add_argument(
        "--reasoning-effort",
        default=settings.deepseek.DIALOGUE_REASONING_EFFORT,
        help="reasoning_effort (пусто — не передавать)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.think = False if args.no_think else settings.deepseek.DIALOGUE_THINK

    if args.dump:
        if not args.scene:
            print("Для --dump укажите --scene <ключ>", file=sys.stderr)
            return 2
        return asyncio.run(_run_dump(args))

    if args.export_mock:
        return asyncio.run(_run_db(args))

    if args.scene_id is None:
        print("Укажите --scene-id <id> (или --dump/--export-mock)", file=sys.stderr)
        return 2

    return asyncio.run(_run_db(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка: {exc}", file=sys.stderr)
        raise SystemExit(1)
