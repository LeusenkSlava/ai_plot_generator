from dataclasses import dataclass
from datetime import datetime

from src.core.generation_jobs.models import GenerationJobStatus


@dataclass(frozen=True, slots=True)
class GenerationJob:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    job_id: int
    status: GenerationJobStatus
    result_id: int | None = None
    error: str | None = None
