import logging

from src.core.generation_jobs.interfaces import GenerationJobRepositoryProtocol
from src.core.generation_jobs.models import GenerationJob, GenerationJobStatus
from src.core.novels.exceptions import (
    GenerationError,
    NovelFinishedError,
    NovelNotFoundError,
    SceneOrderError,
)
from src.core.novels.interfaces.generation import SceneGenerationLockProtocol
from src.core.novels.services.generation.continuation import SceneContinuationService
from src.core.novels.services.generation.transactions import TransactionFactory

logger = logging.getLogger(__name__)


class GenerateSceneUseCase:
    """Cгенерировать следующую сцену новеллы.

    Взаимоисключение по ``(novel_id, roadmap_id, position)`` держится на
    Redis-блокировке, а генераторы делят работу на короткие read/write-транзакции,
    поэтому соединение Postgres не держится во время LLM-вызовов.
    """

    def __init__(
        self,
        jobs_repo: GenerationJobRepositoryProtocol,
        continuation_service: SceneContinuationService,
        lock: SceneGenerationLockProtocol,
    ):
        self._jobs_repo = jobs_repo
        self._continuation_service = continuation_service
        self._lock = lock

    async def execute(
        self,
        job_id: int,
        novel_id: int,
        roadmap_id: int,
        position: int,
        *,
        step: TransactionFactory,
    ) -> GenerationJob:
        async with step():
            job = await self._jobs_repo.get(job_id)
            if job is not None:
                return job

        # Блокирующий захват: ждёт, пока другой воркер закончит эту же сцену.
        await self._lock.acquire(novel_id, roadmap_id, position)

        try:
            # Повторная проверка под блокировкой: пока ждали, дубль с тем же
            # job_id мог уже завершиться — вернём сохранённый результат.
            async with step():
                job = await self._jobs_repo.get(job_id)
                if job is not None:
                    return job

            try:
                scene = await self._continuation_service.generate(
                    novel_id, roadmap_id, position, step=step
                )
            except (
                GenerationError,
                NovelNotFoundError,
                NovelFinishedError,
                SceneOrderError,
            ) as e:
                logger.error(
                    "Scene generation: job_id=%s novel_id=%s roadmap_id=%s position=%s failed: %s",
                    job_id,
                    novel_id,
                    roadmap_id,
                    position,
                    e,
                )
                async with step():
                    return await self._jobs_repo.create(
                        GenerationJob(
                            id=None,
                            created_at=None,
                            updated_at=None,
                            job_id=job_id,
                            status=GenerationJobStatus.FAILED,
                            error=str(e) or "Generation failed",
                        )
                    )
            async with step():
                return await self._jobs_repo.create(
                    GenerationJob(
                        id=None,
                        created_at=None,
                        updated_at=None,
                        job_id=job_id,
                        status=GenerationJobStatus.DONE,
                        result_id=scene.id,
                    )
                )
        finally:
            await self._lock.release(novel_id, roadmap_id, position)
