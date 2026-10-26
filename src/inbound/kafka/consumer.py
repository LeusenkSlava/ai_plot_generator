from aiokafka import AIOKafkaConsumer
from aiokafka.abc import ConsumerRebalanceListener

from src.inbound.kafka.handlers import CONSUMED_TOPICS
from src.inbound.kafka.tasks.offset_tracker import OffsetTracker
from src.main.config.settings import settings


class RebalanceTrackerListener(ConsumerRebalanceListener):
    """Сбрасывает водяной знак партиции при её отзыве перед ребалансом.

    Воркеры, чьи партиции отозвали, могли завершиться уже после отзыва — их
    оффсеты больше не коммитятся (``OffsetTracker.mark_done`` их игнорирует).
    """

    def __init__(self, tracker: OffsetTracker) -> None:
        self._tracker = tracker

    def on_partitions_revoked(self, revoked) -> None:
        self._tracker.reset(revoked)

    def on_partitions_assigned(self, assigned) -> None:
        # Состояние создаётся лениво при первом mark_inflight — сбрасывать нечего.
        pass


def build_consumer(tracker: OffsetTracker | None = None) -> AIOKafkaConsumer:
    consumer = AIOKafkaConsumer(
        bootstrap_servers=settings.kafka.BOOTSTRAP_SERVERS,
        client_id=settings.kafka.CLIENT_ID,
        group_id=settings.kafka.GROUP_ID,
        # Offset коммитим вручную, только после отправки ответа
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        max_poll_interval_ms=settings.kafka.MAX_POLL_INTERVAL_MS,
    )
    listener = RebalanceTrackerListener(tracker) if tracker is not None else None
    consumer.subscribe(CONSUMED_TOPICS, listener=listener)
    return consumer
