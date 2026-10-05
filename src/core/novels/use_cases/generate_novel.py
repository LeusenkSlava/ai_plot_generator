import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from src.core.generation_jobs.interfaces import GenerationJobRepositoryProtocol
from src.core.generation_jobs.models import GenerationJob, GenerationJobStatus
from src.core.novels.exceptions import GenerationError
from src.core.novels.services.composition import NovelCompositionService

logger = logging.getLogger(__name__)

SavepointFactory = Callable[[], AbstractAsyncContextManager[None]]


class GenerateNovelUseCase:
    """Сценарий: обработать запрос на генерацию новеллы."""

    def __init__(
        self,
        jobs_repo: GenerationJobRepositoryProtocol,
        composition_service: NovelCompositionService,
    ):
        self._jobs_repo = jobs_repo
        self._composition_service = composition_service

    async def execute(
        self,
        job_id: int,
        prompt: str,
        universe_id: int | None,
        *,
        savepoint: SavepointFactory,
    ) -> GenerationJob:
        job = await self._jobs_repo.get(job_id)
        if job is not None:
            return job

        try:
            async with savepoint():
                novel = await self._composition_service.create(prompt, universe_id)
        except GenerationError as e:
            logger.error("Generation job %s failed: %s", job_id, e)
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
