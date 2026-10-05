from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaProducer

from src.core.novels.interfaces.generation_job import GenerationResultSenderProtocol
from src.inbound.kafka.dependencies import (
    build_generate_novel_use_case,
    build_generate_scene_use_case,
)
from src.inbound.kafka.handlers.plot_generation import NovelGenerateHandler
from src.inbound.kafka.handlers.scene_generation import SceneGenerateHandler
from src.outbound.kafka.producers.generation_result_sender import GenerationResultSender
from src.outbound.kafka.topic import Topics

MessageHandler = Callable[[bytes], Awaitable[None]]

CONSUMED_TOPICS: tuple[str, ...] = (Topics.NOVEL_GENERATE, Topics.SCENE_GENERATE)


def build_topic_handlers(producer: AIOKafkaProducer) -> dict[str, MessageHandler]:
    results: GenerationResultSenderProtocol = GenerationResultSender(producer)

    novel_generate_handler = NovelGenerateHandler(
        results=results,
        use_case_factory=build_generate_novel_use_case,
    )
    scene_generate_handler = SceneGenerateHandler(
        results=results,
        use_case_factory=build_generate_scene_use_case,
    )
    return {
        Topics.NOVEL_GENERATE: novel_generate_handler.handle,
        Topics.SCENE_GENERATE: scene_generate_handler.handle,
    }
