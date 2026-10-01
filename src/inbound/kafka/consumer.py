import logging

from aiokafka import AIOKafkaConsumer
from pydantic import ValidationError

from src.inbound.kafka.handlers.registry import HANDLERS
from src.main.config.settings import settings
from src.outbound.kafka.topic import Topics

logger = logging.getLogger(__name__)

def build_consumer() -> AIOKafkaConsumer:
    # Создаётся только внутри запущенного event loop (lifespan):
    # на Python 3.14 AIOKafkaConsumer падает при создании без активного цикла.
    return AIOKafkaConsumer(
        Topics.NOVEL_EVENTS_CREATE,
        bootstrap_servers=settings.kafka.BOOTSTRAP_SERVERS,
        group_id="ai_plot_generator_group",
    )


async def consume_loop(consumer: AIOKafkaConsumer):
    async for msg in consumer:
        schema, handler = HANDLERS[msg.topic]
        try:
            payload = schema.model_validate_json(msg.value)
        except ValidationError:
            logger.exception("Невалидное сообщение в %s: %r", msg.topic, msg.value)
            await consumer.commit()
            continue

        try:
            await handler(payload)
        except Exception:
            logger.exception("Ошибка обработки %s", msg.topic)
            continue

        await consumer.commit()
