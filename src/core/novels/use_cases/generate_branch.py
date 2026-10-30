import logging

from src.core.generation_jobs.interfaces import GenerationJobRepositoryProtocol
from src.core.generation_jobs.models import GenerationJob, GenerationJobStatus
from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import BranchGenerationLockProtocol
from src.core.novels.services.crud import RoadmapChoiceService
from src.core.novels.services.generation.generators.branch_roadmap import (
    BranchRoadmapGenerator,
)
from src.core.novels.services.generation.transactions import TransactionFactory

logger = logging.getLogger(__name__)


class GenerateBranchUseCase:
    """Сгенерировать альтернативную ветку роадмапа для выбранного варианта.

    Идемпотентно по ``job_id`` (generation_jobs) и по факту: если у варианта уже
    проставлен ``next_roadmap_id`` — ветка готова, возвращаем сохранённый результат.
    Взаимоисключение по ``(novel_id, roadmap_choice_id)`` держится на Redis.
    """

    def __init__(
        self,
        jobs_repo: GenerationJobRepositoryProtocol,
        choice_service: RoadmapChoiceService,
        branch_generator: BranchRoadmapGenerator,
        lock: BranchGenerationLockProtocol,
    ):
        self._jobs_repo = jobs_repo
        self._choice_service = choice_service
        self._branch_generator = branch_generator
        self._lock = lock

    async def execute(
        self,
        job_id: int,
        novel_id: int,
        roadmap_choice_id: int,
        *,
        step: TransactionFactory,
    ) -> GenerationJob:
        async with step():
            job = await self._jobs_repo.get(job_id)
            if job is not None:
                return job

        await self._lock.acquire(novel_id, roadmap_choice_id)

        try:
            # Повторная проверка под блокировкой.
            async with step():
                job = await self._jobs_repo.get(job_id)
                if job is not None:
                    return job

            async with step():
                choice = await self._choice_service.get(roadmap_choice_id)
            if choice is None:
                error = f"Roadmap choice {roadmap_choice_id} not found"
                logger.error("Branch generation: job_id=%s failed: %s", job_id, error)
                async with step():
                    return await self._jobs_repo.create(
                        GenerationJob(
                            id=None,
                            created_at=None,
                            updated_at=None,
                            job_id=job_id,
                            status=GenerationJobStatus.FAILED,
                            error=error,
                        )
                    )

            # Ветка уже материализована (повторная доставка / дубль) — идемпотентность.
            if choice.next_roadmap_id is not None:
                async with step():
                    return await self._jobs_repo.create(
                        GenerationJob(
                            id=None,
                            created_at=None,
                            updated_at=None,
                            job_id=job_id,
                            status=GenerationJobStatus.DONE,
                            result_id=choice.next_roadmap_id,
                        )
                    )

            try:
                branch = await self._branch_generator.generate(
                    roadmap_choice_id, step=step
                )
            except GenerationError as e:
                logger.error(
                    "Branch generation: job_id=%s roadmap_choice_id=%s failed: %s",
                    job_id,
                    roadmap_choice_id,
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
                            error=str(e) or "Branch generation failed",
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
                        result_id=branch[0].id,
                    )
                )
        finally:
            await self._lock.release(novel_id, roadmap_choice_id)
