import asyncio
import logging
import time

from src.core.generation_jobs.interfaces import GenerationJobRepositoryProtocol
from src.core.generation_jobs.models import GenerationJob, GenerationJobStatus
from src.core.novels.exceptions import (
    GenerationInProgressError,
    NovelGenerationFailedError,
)
from src.core.novels.interfaces.generation import JobLockProtocol
from src.core.novels.interfaces.repository import NovelRepositoryProtocol
from src.core.novels.services.generation.composition import NovelCompositionService
from src.core.novels.services.generation.transactions import TransactionFactory

logger = logging.getLogger(__name__)


class GenerateNovelUseCase:
    """Сценарий: обработать запрос на генерацию новеллы (Saga с компенсацией).

    Вместо одной транзакции на весь пайплайн каждый шаг коммитится отдельно
    (``step``), а взаимоисключение по ``job_id`` обеспечивает Redis-блокировка.
    При сбое удаляем частично созданную новеллу (компенсация) и пишем FAILED.
    """

    def __init__(
        self,
        jobs_repo: GenerationJobRepositoryProtocol,
        novel_repository: NovelRepositoryProtocol,
        composition_service: NovelCompositionService,
        lock: JobLockProtocol,
        *,
        in_progress_poll_interval_s: float = 1.0,
        in_progress_timeout_s: float = 120.0,
    ):
        self._jobs_repo = jobs_repo
        self._novel_repository = novel_repository
        self._composition_service = composition_service
        self._lock = lock
        self._in_progress_poll_interval_s = in_progress_poll_interval_s
        self._in_progress_timeout_s = in_progress_timeout_s

    async def execute(
        self,
        job_id: int,
        prompt: str,
        universe_id: int | None,
        *,
        step: TransactionFactory,
    ) -> GenerationJob:
        async with step():
            job = await self._jobs_repo.get(job_id)
            if job is not None:
                return job

        if not await self._lock.acquire(job_id):
            return await self._wait_for_job(job_id, step)

        try:
            # Повторная проверка под блокировкой (double-checked locking): между
            # первым get и захватом лока другой воркер мог уже завершить джоб.
            async with step():
                job = await self._jobs_repo.get(job_id)
                if job is not None:
                    return job

            try:
                novel = await self._composition_service.create(
                    prompt, universe_id, step=step
                )
            except NovelGenerationFailedError as e:
                logger.error("Generation job %s failed: %s", job_id, e)
                async with step():
                    if e.novel_id is not None:
                        await self._novel_repository.delete(e.novel_id)
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
                        result_id=novel.id,
                    )
                )
        finally:
            await self._lock.release(job_id)

    async def _wait_for_job(
        self, job_id: int, step: TransactionFactory
    ) -> GenerationJob:
        """Ждёт, пока другой воркер допишет DONE/FAILED, и возвращает сохранённый результат.

        Не держит соединение Postgres: каждая проверка — короткая отдельная транзакция.
        """
        deadline = time.monotonic() + self._in_progress_timeout_s
        while time.monotonic() < deadline:
            await asyncio.sleep(self._in_progress_poll_interval_s)
            async with step():
                job = await self._jobs_repo.get(job_id)
                if job is not None:
                    return job
        raise GenerationInProgressError(
            f"job {job_id} is still being processed by another worker"
        )
