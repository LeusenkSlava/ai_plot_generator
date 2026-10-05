from typing import Protocol

from src.core.generation_jobs.models import GenerationJob


class GenerationResultSenderProtocol(Protocol):
    async def send_job(self, job: GenerationJob) -> None: ...

    async def send_failed(self, job_id: int, error: str) -> None: ...
