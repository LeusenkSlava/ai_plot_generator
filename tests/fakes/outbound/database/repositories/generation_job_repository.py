import dataclasses

from src.core.generation_jobs.models import GenerationJob


class FakeGenerationJobRepository:
    def __init__(self) -> None:
        # ключ — job_id (как в реальном репозитории), id — суррогатный ключ БД
        self._items: dict[int, GenerationJob] = {}
        self._next_id = 1

    async def get(self, job_id: int) -> GenerationJob | None:
        return self._items.get(job_id)

    async def create(self, generation_job: GenerationJob) -> GenerationJob:
        stored = dataclasses.replace(generation_job, id=self._next_id)
        self._next_id += 1
        self._items[generation_job.job_id] = stored
        return stored

    @property
    def saved(self) -> list[GenerationJob]:
        return list(self._items.values())
