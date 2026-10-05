import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from src.core.generation_jobs.interfaces import GenerationJobRepositoryProtocol
from src.core.generation_jobs.models import GenerationJob, GenerationJobStatus
from src.core.novels.exceptions import (
    GenerationError,
    NovelFinishedError,
    NovelNotFoundError,
    SceneOrderError,
)
from src.core.novels.services.continuation import SceneContinuationService

logger = logging.getLogger(__name__)

SavepointFactory = Callable[[], AbstractAsyncContextManager[None]]


class GenerateSceneUseCase:
    """Cгенерировать следующую сцену новеллы."""

    def __init__(
        self,
        jobs_repo: GenerationJobRepositoryProtocol,
        continuation_service: SceneContinuationService,
    ):
        self._jobs_repo = jobs_repo
        self._continuation_service = continuation_service

    async def execute(
        self,
        job_id: int,
        novel_id: int,
        scene_order: int,
        *,
        savepoint: SavepointFactory,
    ) -> GenerationJob:
        job = await self._jobs_repo.get(job_id)
        if job is not None:
            return job

        try:
            async with savepoint():
                scene = await self._continuation_service.generate(novel_id, scene_order)
        except (
            GenerationError,
            NovelNotFoundError,
            NovelFinishedError,
            SceneOrderError,
        ) as e:
            logger.error(
                "Scene generation: job_id=%s novel_id=%s scene_order=%s failed: %s",
                job_id,
                novel_id,
                scene_order,
                e,
            )
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
                result_id=scene.id,
            )
        )
