import logging

from src.core.novels.exceptions import NovelGenerationError
from src.inbound.kafka.handlers.dependencies import build_novel_composition_service
from src.outbound.database.dependencies import get_session_scope
from src.outbound.kafka.schemas.novel_creation import NovelCreateRequested

logger = logging.getLogger(__name__)


async def handle_novel_create_requested(
    payload: NovelCreateRequested,
) -> None:
    try:
        async with get_session_scope() as session:
            service = build_novel_composition_service(session)
            await service.create(payload.prompt)

    except NovelGenerationError as e:
        logger.error(
            "handle_novel_create_requested: %s",
            e,
        )
