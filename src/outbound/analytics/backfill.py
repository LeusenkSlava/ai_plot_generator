"""Одноразовый импорт уже существующих llm_logs/*.jsonl в Kafka-топик аналитики.

Запускается автоматически при старте приложения, до начала обработки новых
задач генерации. Факт успешного завершения фиксируется маркером
``.analytics_backfill_done`` в каталоге логов, чтобы при перезапуске не
отправлять одни и те же события повторно.

Чтобы импортировать данные заново, удалите маркер и перезапустите сервис.
"""

import json
import logging
import os
from pathlib import Path

from aiokafka import AIOKafkaProducer

from src.outbound.analytics.usage_publisher import build_usage_event

logger = logging.getLogger(__name__)

LOG_DIR = Path(os.getenv("LLM_LOG_DIR", "llm_logs"))
_MARKER = ".analytics_backfill_done"


def _entity_id_from_file(path: Path) -> int | None:
    """novel_<id>.jsonl -> id, unassigned.jsonl -> None."""
    stem = path.stem
    if stem == "unassigned":
        return None
    if stem.startswith("novel_"):
        try:
            return int(stem.removeprefix("novel_"))
        except ValueError:
            return None
    return None


def _iter_records(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


async def backfill_usage_logs(
    *,
    producer: AIOKafkaProducer,
    topic: str,
    service: str,
) -> int:
    """Отправляет все существующие записи llm_logs/*.jsonl в топик аналитики.

    Возвращает число отправленных событий. Ошибки только логируются и не
    ломают запуск: при неудаче маркер не пишется, и импорт повторится при
    следующем старте.
    """
    marker = LOG_DIR / _MARKER
    if marker.exists():
        return 0

    files = sorted(LOG_DIR.glob("*.jsonl"))
    if not files:
        # Логировать нечего — фиксируем, чтобы не сканировать пустой каталог повторно.
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            marker.write_text("done", encoding="utf-8")
        except OSError as exc:
            logger.error("usage backfill: не удалось записать маркер: %s", exc)
        return 0

    sent = 0
    try:
        for path in files:
            entity_id = _entity_id_from_file(path)
            for record in _iter_records(path):
                event = build_usage_event(
                    record,
                    entity_id=entity_id,
                    service=service,
                )
                await producer.send_and_wait(
                    topic,
                    json.dumps(event, ensure_ascii=False, default=str).encode(),
                )
                sent += 1
            logger.info("usage backfill: %s (entity_id=%s)", path.name, entity_id)
        marker.write_text("done", encoding="utf-8")
        logger.info("usage backfill: отправлено %d событий в %s", sent, topic)
    except Exception as exc:
        logger.error(
            "usage backfill: прервано после %d событий, будет повторено при "
            "следующем старте: %s",
            sent,
            exc,
        )
    return sent
