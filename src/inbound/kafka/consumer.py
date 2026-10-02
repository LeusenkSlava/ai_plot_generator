from aiokafka import AIOKafkaConsumer

from src.inbound.kafka.handlers import CONSUMED_TOPICS
from src.main.config.settings import settings


def build_consumer() -> AIOKafkaConsumer:
    return AIOKafkaConsumer(
        *CONSUMED_TOPICS,
        bootstrap_servers=settings.kafka.BOOTSTRAP_SERVERS,
        client_id=settings.kafka.CLIENT_ID,
        group_id=settings.kafka.GROUP_ID,
        # Offset коммитим вручную, только после отправки ответа
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
