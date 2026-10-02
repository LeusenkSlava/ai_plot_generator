import json
import logging

from aiokafka import AIOKafkaProducer
from pydantic import ValidationError

from src.core.novels.exceptions import GenerationError
from src.inbound.kafka.dependencies import build_novel_composition_service
from src.outbound.database.dependencies import get_session_scope
from src.outbound.database.repositories.generation_job_repository import (
    GenerationJobRepository,
)
from src.outbound.kafka.schemas.novel_creation import (
    GenerationResult,
    NovelGenerateRequested,
)
from src.outbound.kafka.topic import Topics

logger = logging.getLogger(__name__)


class NovelGenerateHandler:
    """Обрабатывает запрос на генерацию новеллы и всегда отвечает в generation.results"""

    def __init__(self, producer: AIOKafkaProducer):
        self._producer = producer

    async def handle(self, raw: bytes) -> None:
        """Обрабатывает запрос на генерацию новеллы и всегда отвечает в generation.results"""
        try:
            payload = NovelGenerateRequested.model_validate_json(raw)
        except ValidationError as e:
            job_id = _extract_job_id(raw)
            if job_id is None:
                logger.error("Job_id missing in message, skipping: %r", raw[:500])
                return
            await self._reply_failed(job_id, f"Incorrect request: {e}")
            return

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

        await self._send(
            GenerationResult(
                job_id=_job_id_for_reply(payload.job_id),
                status=job.status,
                result_id=job.result_id,
                error=job.error,
            )
        )

    async def _reply_failed(self, job_id: str, error: str) -> None:
        await self._send(
            GenerationResult(
                job_id=_job_id_for_reply(job_id), status="failed", error=error
            )
        )

    async def _send(self, result: GenerationResult) -> None:
        await self._producer.send_and_wait(
            Topics.GENERATION_RESULTS,
            result.model_dump_json(exclude_none=True).encode(),
            key=str(result.job_id).encode(),
        )


def _extract_job_id(raw: bytes) -> str | None:
    try:
        job_id = json.loads(raw).get("job_id")
    except ValueError, AttributeError:
        return None
    return str(job_id) if job_id not in (None, "") else None


def _job_id_for_reply(job_id: str) -> int | str:
    return int(job_id) if job_id.isdigit() else job_id
