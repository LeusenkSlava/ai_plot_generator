import logging

from aiokafka import AIOKafkaProducer
from pydantic import ValidationError

from src.core.novels.exceptions import (
    GenerationError,
    NovelFinishedError,
    NovelNotFoundError,
    SceneOrderError,
)
from src.inbound.kafka.dependencies import build_scene_continuation_service
from src.inbound.kafka.handlers.results import GenerationResultSender, extract_job_id
from src.outbound.database.dependencies import get_session_scope
from src.outbound.database.repositories.generation_job_repository import (
    GenerationJobRepository,
)
from src.outbound.kafka.schemas.scene_generation import SceneGenerateRequested

logger = logging.getLogger(__name__)


class SceneGenerateHandler:
    """Генерирует следующую сцену новеллы и всегда отвечает в generation.results.

    Идемпотентность:
    - по job_id: повторная доставка того же сообщения переотправляет сохранённый результат;
    - по (novel_id, scene_order): сцена генерируется под advisory-блокировкой, вторая команда
      на ту же сцену ждёт окончания первой и получает done с id уже готовой сцены.
    Результат отправляется только после коммита сцены со всеми репликами.
    """

    def __init__(self, producer: AIOKafkaProducer):
        self._results = GenerationResultSender(producer)

    async def handle(self, raw: bytes) -> None:
        try:
            payload = SceneGenerateRequested.model_validate_json(raw)
        except ValidationError as e:
            job_id = extract_job_id(raw)
            if job_id is None:
                logger.error("Job_id missing in message, skipping: %r", raw[:500])
                return
            await self._results.send_failed(job_id, f"Incorrect request: {e}")
            return

        ctx = (payload.job_id, payload.novel_id, payload.scene_order)
        logger.info("Scene generation: job_id=%s novel_id=%s scene_order=%s received", *ctx)

        async with get_session_scope() as session:
            jobs_repo = GenerationJobRepository(session)
            job = await jobs_repo.get(payload.job_id)
            if job is not None:
                logger.info(
                    "Scene generation: job_id=%s novel_id=%s scene_order=%s "
                    "already processed, resending result",
                    *ctx,
                )
            else:
                service = build_scene_continuation_service(session)
                try:
                    async with session.begin_nested():
                        scene, created = await service.generate(
                            payload.novel_id, payload.scene_order
                        )
                except (
                    GenerationError,
                    NovelNotFoundError,
                    NovelFinishedError,
                    SceneOrderError,
                ) as e:
                    logger.error(
                        "Scene generation: job_id=%s novel_id=%s scene_order=%s failed: %s",
                        *ctx,
                        e,
                    )
                    job = await jobs_repo.save(
                        payload.job_id, "failed", error=str(e) or "Generation failed"
                    )
                else:
                    logger.info(
                        "Scene generation: job_id=%s novel_id=%s scene_order=%s "
                        "done, scene_id=%s, created=%s",
                        *ctx,
                        scene.id,
                        created,
                    )
                    job = await jobs_repo.save(payload.job_id, "done", result_id=scene.id)
        # Выход из get_session_scope — коммит сцены, реплик и job; блокировка снимается здесь же

        await self._results.send_job(job)
