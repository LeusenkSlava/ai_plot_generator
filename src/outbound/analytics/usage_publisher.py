"""Публикация событий использования LLM в Kafka для отдельного сервиса аналитики.

Адаптер протокола LLMUsagePublisher: отправляет сообщение fire-and-forget
(без ожидания подтверждения), а любые ошибки доставки только логирует —
аналитика не должна влиять на генерацию.

Событие строго соответствует схеме ClickHouse ``analytics.llm_calls``: лишние
поля не отправляются, чтобы JSONEachRow-потребитель не отбрасывал сообщения.
"""

import asyncio
import json
import logging

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


def build_usage_event(
    record: dict,
    *,
    entity_id: int | None,
    service: str,
) -> dict:
    """Собирает событие аналитики в формате analytics.llm_calls.

    Маппинг записи llm_log на колонки ClickHouse:
      - ``service``          <- идентификатор сервиса (app.SERVICE_ID)
      - ``cached_tokens``    <- cache_hit_tokens (токены, попавшие в кэш)
      - ``duration_ms``      <- duration_s * 1000
      - ``llm_requests``     <- 1 на вызов, ``tool_calls`` <- 0
      - ``job_id``           <- пока пусто (job_id можно протянуть в trace позже)
    """
    duration_s = record.get("duration_s") or 0
    return {
        "ts": record.get("ts"),
        "service": service,
        "operation": record.get("operation") or "",
        "step": record.get("step") or "",
        "model": record.get("model") or "",
        "entity_id": str(entity_id) if entity_id is not None else "",
        "job_id": str(record.get("job_id") or ""),
        "prompt_tokens": int(record.get("prompt_tokens") or 0),
        "completion_tokens": int(record.get("completion_tokens") or 0),
        "cached_tokens": int(record.get("cache_hit_tokens") or 0),
        "duration_ms": int(round(duration_s * 1000)),
        "llm_requests": 1,
        "tool_calls": 0,
        "error": record.get("error") or "",
    }


class KafkaLLMUsagePublisher:
    """Отправляет события использования LLM в Kafka без ожидания ответа."""

    def __init__(self, producer: AIOKafkaProducer, topic: str, service: str):
        self._producer = producer
        self._topic = topic
        self._service = service
        self._tasks: set[asyncio.Task] = set()

    def publish(self, record: dict, entity_id: int | None) -> None:
        """Планирует отправку события в текущем event loop, не дожидаясь результата."""
        event = build_usage_event(record, entity_id=entity_id, service=self._service)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.error("usage_publisher: нет запущенного event loop — событие пропущено")
            return
        task = loop.create_task(self._send(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def flush(self) -> None:
        """Дожидается отправки всех запланированных событий (перед остановкой продюсера)."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _send(self, event: dict) -> None:
        try:
            await self._producer.send(
                self._topic,
                json.dumps(event, ensure_ascii=False, default=str).encode(),
            )
        except Exception as exc:  # аналитика не должна ломать генерацию
            logger.error("usage_publisher: не удалось отправить событие: %s", exc)
