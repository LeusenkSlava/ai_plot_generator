from typing import Protocol

from src.core.generation_jobs.models import GenerationJob


class GenerationJobRepositoryProtocol(Protocol):
    async def get(self, job_id: int) -> GenerationJob | None: ...
    async def create(self, generation_job: GenerationJob) -> GenerationJob: ...
