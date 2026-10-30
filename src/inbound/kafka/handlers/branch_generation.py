import logging
from collections.abc import Callable

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.novels.use_cases import GenerateBranchUseCase
from src.inbound.kafka.dependencies import build_generate_branch_use_case
from src.inbound.kafka.schemas import BranchGenerateRequestedSchema
from src.inbound.kafka.utils import extract_job_id
from src.outbound.database.dependencies import get_session_scope
from src.outbound.kafka.producers.generation_result_sender import GenerationResultSender

logger = logging.getLogger(__name__)

UseCaseFactory = Callable[[AsyncSession], GenerateBranchUseCase]


class BranchGenerateHandler:
    """Генерирует альтернативную ветку роадмапа и отвечает в generation.results."""

    def __init__(
        self,
        results: GenerationResultSender,
        use_case_factory: UseCaseFactory = build_generate_branch_use_case,
    ):
        self._results = results
        self._use_case_factory = use_case_factory

    async def handle(self, raw: bytes) -> None:
        schema = await self._parse_or_fail(raw)
        if schema is None:
            return

        async with get_session_scope() as session:
            use_case = self._use_case_factory(session)
            job = await use_case.execute(
                job_id=schema.job_id,
                novel_id=schema.novel_id,
                roadmap_choice_id=schema.roadmap_choice_id,
                step=session.begin,
            )

        await self._results.send_job(job)

    async def _parse_or_fail(self, raw: bytes) -> BranchGenerateRequestedSchema | None:
        try:
            return BranchGenerateRequestedSchema.model_validate_json(raw)
        except ValidationError as e:
            job_id = extract_job_id(raw)
            if job_id is None:
                logger.error("Job_id missing in message, skipping: %r", raw[:500])
                return None
            await self._results.send_failed(job_id, f"Incorrect request: {e}")
            return None
