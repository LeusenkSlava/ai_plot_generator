from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaProducer

from src.inbound.kafka.handlers.plot_generation import NovelGenerateHandler
from src.inbound.kafka.handlers.scene_generation import SceneGenerateHandler
from src.outbound.kafka.topic import Topics

MessageHandler = Callable[[bytes], Awaitable[None]]

CONSUMED_TOPICS: tuple[str, ...] = (Topics.NOVEL_GENERATE, Topics.SCENE_GENERATE)


def build_topic_handlers(producer: AIOKafkaProducer) -> dict[str, MessageHandler]:
    novel_generate_handler = NovelGenerateHandler(producer)
    scene_generate_handler = SceneGenerateHandler(producer)

    return {
        Topics.NOVEL_GENERATE: novel_generate_handler.handle,
        Topics.SCENE_GENERATE: scene_generate_handler.handle,
    }
