from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.outbound.database.models.generation_jobs import GenerationJobModel


class GenerationJobRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, job_id: str) -> GenerationJobModel | None:
        result = await self._session.execute(
            select(GenerationJobModel).where(GenerationJobModel.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def save(
        self,
        job_id: str,
        status: str,
        result_id: int | None = None,
        error: str | None = None,
    ) -> GenerationJobModel:
        job = GenerationJobModel(
            job_id=job_id, status=status, result_id=result_id, error=error
        )
        self._session.add(job)
        await self._session.flush()
        return job
