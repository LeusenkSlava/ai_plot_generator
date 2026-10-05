from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.generation_jobs.models import GenerationJob
from src.outbound.database.models.generation_jobs import GenerationJobModel


class GenerationJobRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, job_id: int) -> GenerationJob | None:
        result = await self._session.execute(
            select(GenerationJobModel).where(GenerationJobModel.job_id == job_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create(
        self,
        generation_job: GenerationJob,
    ) -> GenerationJob:
        job = GenerationJobModel(
            job_id=generation_job.job_id,
            status=generation_job.status,
            result_id=generation_job.result_id,
            error=generation_job.error,
        )
        self._session.add(job)
        await self._session.flush()
        return self._to_domain(job)

    @staticmethod
    def _to_domain(model: GenerationJobModel) -> GenerationJob:
        return GenerationJob(
            id=model.id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            job_id=model.job_id,
            status=model.status,
            result_id=model.result_id,
            error=model.error,
        )
