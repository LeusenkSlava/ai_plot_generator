import asyncio
import logging

from aiokafka import AIOKafkaConsumer

from src.inbound.kafka.handlers import MessageHandler

logger = logging.getLogger(__name__)


async def consume_loop(
    consumer: AIOKafkaConsumer, handlers: dict[str, MessageHandler]
) -> None:
    async for msg in consumer:
        topic = msg.topic
        handler = handlers.get(topic)
        if handler is None:
            logger.warning("Нет обработчика для топика %s, пропускаем", topic)
        else:
            await _handle_with_retry(handler, msg)
        await consumer.commit()


async def _handle_with_retry(handler: MessageHandler, msg) -> None:
    delay = 1.0
    while True:
        try:
            await handler(msg.value)
            return
        except Exception:
            logger.exception(
                "Ошибка обработки %s[%s]@%s, повтор через %.0fс",
                msg.topic,
                msg.partition,
                msg.offset,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
