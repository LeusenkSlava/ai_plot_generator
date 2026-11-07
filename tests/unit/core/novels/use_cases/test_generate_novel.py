"""Автор из Kafka-команды доходит до саги генерации новеллы."""

from src.core.generation_jobs.models import GenerationJobStatus
from src.core.novels.models import (
    DEFAULT_PROMPT_VARIANT,
    Novel,
    NovelMode,
)
from src.core.novels.services.generation.transactions import noop_step
from src.core.novels.use_cases.generate_novel import GenerateNovelUseCase
from tests.fakes.outbound.database.repositories.generation_job_repository import (
    FakeGenerationJobRepository,
)
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)


class _RecordingComposition:
    def __init__(self) -> None:
        self.author_ids: list[int | None] = []

    async def create(
        self,
        user_prompt: str,
        universe_id: int | None = None,
        mode: NovelMode = NovelMode.LINEAR,
        prompt_variant: str = DEFAULT_PROMPT_VARIANT,
        author_id: int | None = None,
        *,
        step,
    ) -> Novel:
        self.author_ids.append(author_id)
        return Novel(
            id=1,
            created_at=None,
            updated_at=None,
            title="Новелла",
            public_description="",
            description="d",
            tone="t",
            author_id=author_id,
        )


class _AlwaysAcquiredLock:
    async def acquire(self, job_id: int) -> bool:
        return True

    async def release(self, job_id: int) -> None:
        return None


def _use_case(composition: _RecordingComposition) -> GenerateNovelUseCase:
    return GenerateNovelUseCase(
        jobs_repo=FakeGenerationJobRepository(),
        novel_repository=FakeNovelRepository(),
        composition_service=composition,
        lock=_AlwaysAcquiredLock(),
    )


async def test_author_id_passed_to_composition():
    composition = _RecordingComposition()
    use_case = _use_case(composition)

    job = await use_case.execute(
        job_id=1,
        prompt="история",
        universe_id=None,
        author_id=7,
        step=noop_step,
    )

    assert composition.author_ids == [7]
    assert job.status == GenerationJobStatus.DONE


async def test_missing_author_id_kept_none():
    """Сообщение старого формата не падает: новелла сохраняется без автора."""
    composition = _RecordingComposition()
    use_case = _use_case(composition)

    await use_case.execute(
        job_id=2,
        prompt="история",
        universe_id=None,
        step=noop_step,
    )

    assert composition.author_ids == [None]
