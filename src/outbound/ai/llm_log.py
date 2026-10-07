import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from src.core.novels.interfaces.usage_publisher import LLMUsagePublisher
from src.core.novels.llm_trace import (
    LLMTrace,
    current_step,
    current_trace,
    set_pending_sink,
)

logger = logging.getLogger(__name__)

LOG_DIR = Path(os.getenv("LLM_LOG_DIR", "llm_logs"))

# Регистрируется из main.run при старте; пока не задан — аналитика просто не шлётся.
_usage_publisher: LLMUsagePublisher | None = None


def set_usage_publisher(publisher: LLMUsagePublisher) -> None:
    global _usage_publisher
    _usage_publisher = publisher


def _write(name: str, records: list[dict]) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / f"{name}.jsonl", "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as e:
        logger.error(f"llm_log: failed to write {name}: {e}")


def _publish(records: list[dict], entity_id: int | None) -> None:
    """Отправляет события аналитики в том же месте, где пишется файл.

    Здесь novel_id уже известен (для буферизованных записей — после bind),
    поэтому entity_id заполняется корректно.
    """
    if _usage_publisher is None:
        return
    for record in records:
        try:
            _usage_publisher.publish(record, entity_id)
        except Exception as e:
            logger.error(f"llm_log: usage publish failed: {e}")


def log_llm_call(
    *,
    model: str,
    messages: list,
    response: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    duration_s: float,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    trace = current_trace()
    prompt_chars = sum(
        len(str(m.get("content", ""))) if isinstance(m, dict) else len(str(m))
        for m in messages
    )
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "operation": trace.operation if trace else None,
        "step": current_step(),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
        "prompt_chars": prompt_chars,
        "response_chars": len(response or ""),
        "duration_s": round(duration_s, 2),
        "error": error,
        **(extra or {}),
        "messages": messages,
        "response": response,
    }
    if trace is None:
        _write("unassigned", [record])
        _publish([record], None)
    elif trace.novel_id is None:
        trace.pending.append(record)
    else:
        # Накопленное до создания новеллы пишем вместе с первой записью после bind
        records = [*trace.pending, record]
        _write(f"novel_{trace.novel_id}", records)
        _publish(records, trace.novel_id)
        trace.pending.clear()


def _flush_pending(trace: LLMTrace) -> None:
    name = f"novel_{trace.novel_id}" if trace.novel_id is not None else "unassigned"
    _write(name, trace.pending)
    _publish(trace.pending, trace.novel_id)
    trace.pending.clear()


set_pending_sink(_flush_pending)
