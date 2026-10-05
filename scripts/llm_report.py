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


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def summary() -> None:
    files = sorted(LOG_DIR.glob("*.jsonl"))
    if not files:
        print(f"Нет логов в {LOG_DIR}")
        return
    print(f"{'файл':<20}{'запросов':>9}{'prompt':>10}{'compl':>9}{'всего':>10}{'ошибок':>8}")
    grand = 0
    for f in files:
        rows = load(f)
        p = sum(r["prompt_tokens"] or 0 for r in rows)
        c = sum(r["completion_tokens"] or 0 for r in rows)
        errors = sum(1 for r in rows if r["error"])
        grand += p + c
        print(f"{f.stem:<20}{len(rows):>9}{p:>10}{c:>9}{p + c:>10}{errors:>8}")
    print(f"\nВсего токенов: {grand}")


def details(novel_id: str, full: bool) -> None:
    rows = load(LOG_DIR / f"novel_{novel_id}.jsonl")
    print(f"{'#':>3} {'время':<20}{'операция':<14}{'шаг':<24}{'prompt':>8}{'compl':>7}{'симв.':>8}{'сек':>7}")
    for i, r in enumerate(rows, 1):
        print(
            f"{i:>3} {r['ts'][:19]:<20}{r['operation'] or '-':<14}{r['step'] or '-':<24}"
            f"{r['prompt_tokens'] or 0:>8}{r['completion_tokens'] or 0:>7}"
            f"{r['prompt_chars']:>8}{r['duration_s']:>7}" + (f"  ERROR: {r['error']}" if r["error"] else "")
        )
        if full:
            for m in r["messages"]:
                print(f"--- [{m.get('role')}]\n{m.get('content')}")
            print(f"=== ответ:\n{r['response']}\n")
    by_step: dict[str, list[int]] = {}
    for r in rows:
        s = by_step.setdefault(r["step"] or "-", [0, 0])
        s[0] += 1
        s[1] += (r["prompt_tokens"] or 0) + (r["completion_tokens"] or 0)
    print("\nПо шагам:")
    for step, (n, t) in sorted(by_step.items(), key=lambda x: -x[1][1]):
        print(f"  {step:<24}{n:>4} запр.{t:>10} ток.")
    print(f"Итого: {len(rows)} запросов, {sum(t for _, t in by_step.values())} токенов")


def export_md(novel_id: str) -> None:
    rows = load(LOG_DIR / f"novel_{novel_id}.jsonl")
    out = [f"# Новелла {novel_id}: запросы к LLM\n"]
    total = sum((r["prompt_tokens"] or 0) + (r["completion_tokens"] or 0) for r in rows)
    out.append(f"Запросов: {len(rows)}, токенов: {total}\n")
    for i, r in enumerate(rows, 1):
        out.append(
            f"\n## {i}. {r['operation'] or '-'} / {r['step'] or '-'}\n\n"
            f"prompt: {r['prompt_tokens']} ток. ({r['prompt_chars']} симв.), "
            f"ответ: {r['completion_tokens']} ток., {r['duration_s']} с"
            + (f", ОШИБКА: {r['error']}" if r["error"] else "")
            + "\n"
        )
        for m in r["messages"]:
            content = str(m.get("content"))
            out.append(f"\n### [{m.get('role')}] — {len(content)} симв.\n\n````\n{content}\n````\n")
        response = r["response"] or ""
        try:
            response = json.dumps(json.loads(response), ensure_ascii=False, indent=2)
        except ValueError:
            pass
        out.append(f"\n### Ответ\n\n````\n{response}\n````\n")
    path = LOG_DIR / f"novel_{novel_id}.md"
    path.write_text("".join(out), encoding="utf-8")
    print(f"Записано: {path}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and "--md" in sys.argv:
        export_md(args[0])
    elif args:
        details(args[0], "--full" in sys.argv)
    else:
        summary()
