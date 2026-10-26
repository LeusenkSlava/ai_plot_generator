import asyncio
import logging

from aiokafka import AIOKafkaConsumer, TopicPartition

from src.inbound.kafka.handlers import MessageHandler
from src.inbound.kafka.schemas import SceneGenerateRequestedSchema
from src.inbound.kafka.tasks.keyed_locks import KeyedLocks
from src.inbound.kafka.tasks.offset_tracker import OffsetTracker
from src.outbound.kafka.producers.dlq_sender import DlqSender
from src.outbound.kafka.topic import Topics

logger = logging.getLogger(__name__)


def _routing_key(topic: str, raw: bytes) -> int | None:
    """Ключ сериализации обработки. Сцены одной новеллы идут строго по порядку.

    Для остальных топиков ключа нет — сообщения независимы и идут параллельно.
    Невалидное сообщение возвращает ``None``: обработчик сам ответит failed.
    """
    if topic == Topics.SCENE_GENERATE:
        try:
            return SceneGenerateRequestedSchema.model_validate_json(raw).novel_id
        except Exception:
            return None
    return None


async def _commit_watermark(
    tracker: OffsetTracker,
    consumer: AIOKafkaConsumer,
    tp: TopicPartition,
    offset: int,
    commit_lock: asyncio.Lock,
) -> None:
    """Помечает оффсет завершённым и коммитит непрерывный префикс партиции.

    Коммитим не «каждое сообщение», а водяной знак: только если завершённый
    оффсет закрыл очередную дырку в непрерывном префиксе. Коммиты сериализуются
    одним локом, чтобы параллельные воркеры не могли применить коммит меньшего
    оффсета после большего (откат назад → лишняя повторная обработка). Ошибки
    коммита не роняют воркер — сообщение уже обработано, а оффсет будет передан
    повторно при следующем завершённом оффсете.
    """
    tracker.mark_done(tp, offset)
    try:
        next_offset = tracker.watermark(tp)
        if next_offset is not None:
            async with commit_lock:
                await consumer.commit({tp: next_offset})
    except Exception:
        logger.exception(
            "worker: не удалось закоммитить оффсет %s[%s]@%s",
            tp.topic,
            tp.partition,
            offset,
        )


async def consume_loop(
    consumer: AIOKafkaConsumer,
    handlers: dict[str, MessageHandler],
    *,
    concurrency: int = 10,
    max_retries: int = 3,
    retry_base_delay_s: float = 1.0,
    retry_max_delay_s: float = 30.0,
    keyed_locks: KeyedLocks | None = None,
    dlq: DlqSender | None = None,
    tracker: OffsetTracker | None = None,
) -> None:
    """Параллельная обработка сообщений Kafka.

    Фетч и обработка разделены ограниченной очередью размером ``concurrency``:
    фетчер продолжает поллить (и сбрасывать idle-таймер консьюмера), пока в
    очереди есть место, а семафор ограничивает только число воркеров. Это
    снижает риск вылета из consumer group по ``max_poll_interval``: poll
    останавливается только при полном насыщении (очередь + воркеры), а не сразу
    при занятости пула. Оффсеты коммитятся по водяному знаку непрерывно
    завершённого префикса каждой партиции. Сцены одной новеллы сериализуются
    через ``KeyedLocks``; разные новеллы идут параллельно.
    """
    if keyed_locks is None:
        keyed_locks = KeyedLocks()
    if tracker is None:
        tracker = OffsetTracker()
    sem = asyncio.Semaphore(concurrency)
    commit_lock = asyncio.Lock()
    queue: asyncio.Queue = asyncio.Queue(maxsize=concurrency)

    async def worker(msg) -> None:
        tp = TopicPartition(msg.topic, msg.partition)
        cancelled = False
        try:
            handler = handlers.get(msg.topic)
            if handler is None:
                logger.warning("Нет обработчика для топика %s, пропускаем", msg.topic)
                return
            key = _routing_key(msg.topic, msg.value)
            if key is not None:
                await keyed_locks.run_exclusive(
                    key,
                    lambda: _handle_with_retry(
                        handler,
                        msg.value,
                        max_retries,
                        retry_base_delay_s,
                        retry_max_delay_s,
                        dlq,
                        msg.topic,
                    ),
                )
            else:
                await _handle_with_retry(
                    handler,
                    msg.value,
                    max_retries,
                    retry_base_delay_s,
                    retry_max_delay_s,
                    dlq,
                    msg.topic,
                )
        except asyncio.CancelledError:
            # Сообщение не обработано до конца — оффсет не коммитим, иначе при
            # рестарте оно окажется потерянным (нарушится at-least-once).
            cancelled = True
            raise
        except Exception:
            logger.exception(
                "worker: неожиданная ошибка обработки %s[%s]@%s",
                msg.topic,
                msg.partition,
                msg.offset,
            )
        finally:
            if not cancelled:
                await _commit_watermark(
                    tracker, consumer, tp, msg.offset, commit_lock
                )

    workers: set[asyncio.Task] = set()

    async def fetch() -> None:
        async for msg in consumer:
            await queue.put(msg)

    async def dispatch() -> None:
        while True:
            msg = await queue.get()
            await sem.acquire()
            tracker.mark_inflight(
                TopicPartition(msg.topic, msg.partition), msg.offset
            )
            task = asyncio.create_task(worker(msg))
            workers.add(task)
            task.add_done_callback(workers.discard)
            task.add_done_callback(lambda _t: sem.release())

    fetch_task = asyncio.create_task(fetch(), name="kafka-fetch")
    dispatch_task = asyncio.create_task(dispatch(), name="kafka-dispatch")
    try:
        await asyncio.gather(fetch_task, dispatch_task)
    finally:
        # При остановке отменяем фетчер, диспетчер и незавершённых воркеров,
        # чтобы они не трогали уже закрытые producer/engine после shutdown.
        fetch_task.cancel()
        dispatch_task.cancel()
        for task in list(workers):
            task.cancel()
        await asyncio.gather(
            fetch_task, dispatch_task, *workers, return_exceptions=True
        )


async def _handle_with_retry(
    handler: MessageHandler,
    raw: bytes,
    max_retries: int,
    base_delay: float,
    max_delay: float,
    dlq: DlqSender | None,
    topic: str,
) -> None:
    """Обрабатывает сообщение с конечным числом ретраев, после — в DLQ.

    Доменные ошибки (плохой промпт, сбой генерации) обрабатываются внутри
    обработчика и до сюда не доходят: он возвращает failed-джоб и шлёт результат.
    Здесь ловим только транзиентные ошибки (БД, Kafka, сеть).
    """
    delay = base_delay
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            await handler(raw)
            return
        except Exception:
            if attempt >= max_retries:
                logger.exception(
                    "Сообщение из %s не обработано после %d попыток", topic, attempts
                )
                if dlq is not None:
                    await dlq.send(topic, raw, "retries exhausted")
                return
            logger.warning(
                "Ошибка обработки %s, попытка %d/%d, повтор через %.0fс",
                topic,
                attempt + 1,
                attempts,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
