"""Публикация событий использования LLM в Kafka для сервиса аналитики.

Единый адаптер доставки (``AnalyticsSink``): неблокирующе ставит события во
внутреннюю очередь, фоновый воркер отправляет их в Kafka с подтверждением
(``send_and_wait``) и ретраями. При недоступном брокере события уходят в
локальный outbox (``Spool``) и досылаются при следующем дренаже — аналитика
не влияет на генерацию и не теряет данные.

Событие соответствует схеме ClickHouse ``analytics.llm_calls``: помимо метрик
(токены/латентность/ошибка) передаются ``event_id`` (дедуп-ключ), ``scene_order``,
а также полные ``response`` (сырой ответ LLM) и ``messages`` (весь промпт,
сериализованный в JSON-строку) для каждого вызова.
"""

import asyncio
import json
import logging
import uuid

from aiokafka import AIOKafkaProducer

from src.outbound.analytics.spool import Spool

logger = logging.getLogger(__name__)


def _to_int(value) -> int:
    """Безопасное приведение к int: нечисловые значения (в т.ч. MagicMock-строки
    из тестовых записей) дают 0, а не падение."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _scene_order(operation: str | None) -> int:
    """create_novel → 0, scene_N → N (прочее → 0)."""
    if not operation:
        return 0
    if operation == "create_novel":
        return 0
    if operation.startswith("scene_"):
        try:
            return int(operation.removeprefix("scene_"))
        except ValueError:
            return 0
    return 0


def build_usage_event(
    record: dict,
    *,
    entity_id: int | None,
    service: str,
) -> dict:
    """Собирает событие аналитики в формате analytics.llm_calls.

    Маппинг записи llm_log на колонки ClickHouse:
      - ``event_id``        <- uuid вызова (дедуп-ключ, генерится в llm_log)
      - ``scene_order``     <- 0 для create_novel, N для scene_N
      - ``cached_tokens``   <- cache_hit_tokens (токены, попавшие в кэш)
      - ``duration_ms``     <- duration_s * 1000
      - ``response``        <- сырой ответ LLM (для всех шагов)
      - ``messages``        <- весь промпт, сериализованный в JSON-строку
    """
    operation = record.get("operation") or ""
    step = record.get("step") or ""
    duration_s = record.get("duration_s") or 0

    return {
        "event_id": record.get("event_id") or uuid.uuid4().hex,
        "ts": record.get("ts"),
        "service": service,
        "operation": operation,
        "step": step,
        "scene_order": _scene_order(operation),
        "model": record.get("model") or "",
        "entity_id": str(entity_id) if entity_id is not None else "",
        "job_id": str(record.get("job_id") or ""),
        "prompt_tokens": _to_int(record.get("prompt_tokens")),
        "completion_tokens": _to_int(record.get("completion_tokens")),
        "reasoning_tokens": _to_int(record.get("reasoning_tokens")),
        "cached_tokens": _to_int(record.get("cache_hit_tokens")),
        "duration_ms": int(round(duration_s * 1000)),
        "llm_requests": 1,
        "tool_calls": 0,
        "error": record.get("error") or "",
        "response": record.get("response") or "",
        "messages": json.dumps(record.get("messages") or [], ensure_ascii=False),
    }


class AnalyticsSink:
    """Отправляет события использования LLM в Kafka, с локальным outbox-фолбэком."""

    def __init__(
        self,
        producer: AIOKafkaProducer,
        topic: str,
        service: str,
        *,
        spool: Spool,
        flush_interval_s: float = 1.0,
        max_retries: int = 3,
        retry_backoff_s: float = 0.5,
        queue_size: int = 10000,
    ):
        self._producer = producer
        self._topic = topic
        self._service = service
        self._spool = spool
        self._flush_interval_s = flush_interval_s
        self._max_retries = max_retries
        self._retry_backoff_s = retry_backoff_s
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # -- Протокол LLMUsagePublisher --------------------------------------

    def publish(self, record: dict, entity_id: int | None) -> None:
        """Неблокирующе ставит событие в очередь; при переполнении — в outbox."""
        event = build_usage_event(
            record,
            entity_id=entity_id,
            service=self._service,
        )
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._spool.append(event)

    async def flush(self) -> None:
        """Дожимает очередь и outbox (вызывается перед остановкой)."""
        await self._drain_queue()
        await self._drain_spool()

    # -- Жизненный цикл фонового воркера ---------------------------------

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="analytics-sink")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self._drain_queue()
            await self._drain_spool()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._flush_interval_s)
            except asyncio.TimeoutError:
                pass

    async def _drain_queue(self) -> None:
        while True:
            try:
                event = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if not await self._send_with_retry(event):
                self._spool.append(event)

    async def _drain_spool(self) -> None:
        pending = self._spool.read()
        if not pending:
            return
        failed = []
        for event in pending:
            if not await self._send_with_retry(event):
                failed.append(event)
        self._spool.rewrite(failed)

    async def _send_with_retry(self, event: dict) -> bool:
        payload = json.dumps(event, ensure_ascii=False, default=str).encode()
        for attempt in range(1, self._max_retries + 1):
            try:
                await self._producer.send_and_wait(self._topic, payload)
                return True
            except Exception as exc:
                logger.error(
                    "analytics sink: не удалось отправить событие (попытка %s/%s): %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff_s)
        return False
