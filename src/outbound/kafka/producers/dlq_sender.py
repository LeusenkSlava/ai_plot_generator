import logging

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class DlqSender:
    """Отправляет «мёртвые» сообщения (после исчерпания ретраев) в DLQ-топик.

    Исходный топик и текст ошибки кладутся в заголовки, чтобы сообщение можно
    было переиграть в исходный топик вручную.
    """

    def __init__(self, producer: AIOKafkaProducer, topic: str) -> None:
        self._producer = producer
        self._topic = topic

    async def send(self, original_topic: str, raw: bytes, error: str) -> None:
        try:
            await self._producer.send_and_wait(
                self._topic,
                value=raw,
                headers=[
                    ("original_topic", original_topic.encode()),
                    ("error", error.encode()[:2000]),
                ],
            )
        except Exception:
            # Не даём DLQ-отправке уронить воркер: сообщение уже не обработается,
            # но лог позволит найти его вручную.
            logger.exception("DlqSender: не удалось опубликовать в %s", self._topic)
