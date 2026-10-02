import json
import logging

from aiokafka import AIOKafkaProducer

from src.outbound.database.models.generation_jobs import GenerationJobModel
from src.outbound.kafka.schemas.novel_creation import GenerationResult
from src.outbound.kafka.topic import Topics

logger = logging.getLogger(__name__)


class GenerationResultSender:
    """Отправляет результат задачи генерации в generation.results"""

    def __init__(self, producer: AIOKafkaProducer):
        self._producer = producer

    async def send_job(self, job: GenerationJobModel) -> None:
        await self.send(
            GenerationResult(
                job_id=job.job_id,
                status=job.status,
                result_id=job.result_id,
                error=job.error,
            )
        )

    async def send_failed(self, job_id: int, error: str) -> None:
        await self.send(GenerationResult(job_id=job_id, status="failed", error=error))

    async def send(self, result: GenerationResult) -> None:
        await self._producer.send_and_wait(
            Topics.GENERATION_RESULTS,
            result.model_dump_json(exclude_none=True).encode(),
            key=str(result.job_id).encode(),
        )
        logger.info(
            "Result sent: job_id=%s status=%s result_id=%s error=%s",
            result.job_id,
            result.status,
            result.result_id,
            result.error,
        )


def extract_job_id(raw: bytes) -> int | None:
    """job_id из невалидного сообщения — чтобы всё равно ответить failed."""
    try:
        return int(json.loads(raw).get("job_id"))
    except ValueError, TypeError, AttributeError:
        return None
