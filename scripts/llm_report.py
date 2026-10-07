"""Сводка по запросам к LLM из llm_logs/*.jsonl.

uv run python scripts/llm_report.py              # итоги по всем новеллам
uv run python scripts/llm_report.py 42           # все запросы новеллы 42
uv run python scripts/llm_report.py 42 --full    # + тексты промтов и ответов
uv run python scripts/llm_report.py 42 --md      # промты и ответы в llm_logs/novel_42.md
"""

import json
import os
import sys
from pathlib import Path

LOG_DIR = Path(os.getenv("LLM_LOG_DIR", "llm_logs"))

USAGE = """Использование:
  llm_report.py                    # итоги по всем новеллам
  llm_report.py <novel_id>         # список запросов новеллы
  llm_report.py <novel_id> --full  # + тексты промптов и ответов
  llm_report.py <novel_id> --md    # записать отчёт в llm_logs/novel_<id>.md
"""


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"Пропущена битая строка в {path.name}: {exc}", file=sys.stderr)
    return rows


def available_ids() -> list[str]:
    ids = [
        f.stem.removeprefix("novel_")
        for f in LOG_DIR.glob("novel_*.jsonl")
        if f.stem.removeprefix("novel_").isdigit()
    ]
    return sorted(ids, key=int)


def require_rows(novel_id: str) -> list[dict] | None:
    """Возвращает записи новеллы или None, если лога нет (с подсказкой)."""
    path = LOG_DIR / f"novel_{novel_id}.jsonl"
    if not path.exists():
        print(f"Нет логов для новеллы {novel_id}: файл {path} не найден.")
        ids = available_ids()
        if ids:
            print("Доступны логи новелл:", ", ".join(ids))
        else:
            print(f"В каталоге {LOG_DIR} нет ни одного лога.")
        return None
    return load(path)


def summary() -> None:
    files = sorted(LOG_DIR.glob("*.jsonl"))
    if not files:
        print(f"Нет логов в {LOG_DIR}")
        return
    print(
        f"{'файл':<20}{'запросов':>9}{'prompt':>10}{'compl':>9}{'reason':>9}{'кэш':>9}{'всего':>10}{'ошибок':>8}"
    )
    grand = 0
    for f in files:
        rows = load(f)
        p = sum(r.get("prompt_tokens") or 0 for r in rows)
        c = sum(r.get("completion_tokens") or 0 for r in rows)
        k = sum(r.get("cache_hit_tokens") or 0 for r in rows)
        rsn = sum(r.get("reasoning_tokens") or 0 for r in rows)
        errors = sum(1 for r in rows if r.get("error"))
        grand += p + c
        print(
            f"{f.stem:<20}{len(rows):>9}{p:>10}{c:>9}{rsn:>9}{k:>9}{p + c:>10}{errors:>8}"
        )
    print(f"\nВсего токенов: {grand}")


def details(novel_id: str, full: bool) -> None:
    rows = require_rows(novel_id)
    if rows is None:
        return
    print(
        f"{'#':>3} {'время':<20}{'операция':<14}{'шаг':<24}{'prompt':>8}{'compl':>7}{'reason':>8}{'симв.':>8}{'сек':>7}"
    )
    for i, r in enumerate(rows, 1):
        print(
            f"{i:>3} {(r.get('ts') or '')[:19]:<20}{r.get('operation') or '-':<14}{r.get('step') or '-':<24}"
            f"{r.get('prompt_tokens') or 0:>8}{r.get('completion_tokens') or 0:>7}"
            f"{r.get('reasoning_tokens') or 0:>8}"
            f"{r.get('prompt_chars') or 0:>8}{r.get('duration_s') or 0:>7}"
            + (f"  ERROR: {r.get('error')}" if r.get("error") else "")
        )
        if full:
            for m in r.get("messages", []):
                print(f"--- [{m.get('role')}]\n{m.get('content')}")
            print(f"=== ответ:\n{r.get('response')}\n")
    by_step: dict[str, list[int]] = {}
    for r in rows:
        s = by_step.setdefault(r.get("step") or "-", [0, 0, 0])
        s[0] += 1
        s[1] += (r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0)
        s[2] += r.get("cache_hit_tokens") or 0
    print("\nПо шагам:")
    for step, (n, t, k) in sorted(by_step.items(), key=lambda x: -x[1][1]):
        cache = f" (кэш {k})" if k else ""
        print(f"  {step:<24}{n:>4} запр.{t:>10} ток.{cache}")
    print(
        f"Итого: {len(rows)} запросов, {sum(t for _, t, _ in by_step.values())} токенов"
    )


def export_md(novel_id: str) -> None:
    rows = require_rows(novel_id)
    if rows is None:
        return
    out = [f"# Новелла {novel_id}: запросы к LLM\n"]
    total = sum(
        (r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0) for r in rows
    )
    out.append(f"Запросов: {len(rows)}, токенов: {total}\n")
    for i, r in enumerate(rows, 1):
        out.append(
            f"\n## {i}. {r.get('operation') or '-'} / {r.get('step') or '-'}\n\n"
            f"prompt: {r.get('prompt_tokens')} ток. ({r.get('prompt_chars')} симв.), "
            f"ответ: {r.get('completion_tokens')} ток."
            f"{', reasoning: ' + str(r.get('reasoning_tokens')) + ' ток.' if r.get('reasoning_tokens') else ''}"
            f", {r.get('duration_s')} с"
            + (f", ОШИБКА: {r.get('error')}" if r.get("error") else "")
            + "\n"
        )
        for m in r.get("messages", []):
            content = str(m.get("content"))
            out.append(
                f"\n### [{m.get('role')}] — {len(content)} симв.\n\n````\n{content}\n````\n"
            )
        response = r.get("response") or ""
        try:
            response = json.dumps(json.loads(response), ensure_ascii=False, indent=2)
        except ValueError:
            pass
        out.append(f"\n### Ответ\n\n````\n{response}\n````\n")
    path = LOG_DIR / f"novel_{novel_id}.md"
    path.write_text("".join(out), encoding="utf-8")
    print(f"Записано: {path}")


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(USAGE)
        sys.exit(0)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and "--md" in sys.argv:
        export_md(args[0])
    elif args:
        details(args[0], "--full" in sys.argv)
    else:
        summary()
