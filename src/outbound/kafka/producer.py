from aiokafka import AIOKafkaProducer

from src.main.config.settings import settings


def build_producer() -> AIOKafkaProducer:
    return AIOKafkaProducer(
        bootstrap_servers=settings.kafka.BOOTSTRAP_SERVERS,
        client_id=settings.kafka.CLIENT_ID,
    )
