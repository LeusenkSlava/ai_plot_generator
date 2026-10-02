import logging

from aiokafka import AIOKafkaProducer
from pydantic import ValidationError

from src.core.novels.exceptions import GenerationError
from src.inbound.kafka.dependencies import build_novel_composition_service
from src.inbound.kafka.handlers.results import GenerationResultSender, extract_job_id
from src.outbound.database.dependencies import get_session_scope
from src.outbound.database.repositories.generation_job_repository import (
    GenerationJobRepository,
)
from src.outbound.kafka.schemas.novel_creation import NovelGenerateRequested

logger = logging.getLogger(__name__)


class NovelGenerateHandler:
    """Обрабатывает запрос на генерацию новеллы и всегда отвечает в generation.results"""

    def __init__(self, producer: AIOKafkaProducer):
        self._results = GenerationResultSender(producer)

    async def handle(self, raw: bytes) -> None:
        """Обрабатывает запрос на генерацию новеллы и всегда отвечает в generation.results"""
        try:
            payload = NovelGenerateRequested.model_validate_json(raw)
        except ValidationError as e:
            job_id = extract_job_id(raw)
            if job_id is None:
                logger.error("Job_id missing in message, skipping: %r", raw[:500])
                return
            await self._results.send_failed(job_id, f"Incorrect request: {e}")
            return

        logger.info("Novel generation: job_id=%s received", payload.job_id)
        async with get_session_scope() as session:
            jobs_repo = GenerationJobRepository(session)
            job = await jobs_repo.get(payload.job_id)
            if job is None:
                service = build_novel_composition_service(session)
                try:
                    async with session.begin_nested():
                        novel = await service.create(
                            payload.prompt, payload.universe_id
                        )
                except GenerationError as e:
                    logger.error("Generation job %s failed: %s", payload.job_id, e)
                    job = await jobs_repo.save(
                        payload.job_id, "failed", error=str(e) or "Generation failed"
                    )
                else:
                    job = await jobs_repo.save(
                        payload.job_id, "done", result_id=novel.id
                    )
            else:
                logger.info(
                    "Novel generation: job_id=%s already processed, resending result",
                    payload.job_id,
                )

        await self._results.send_job(job)
