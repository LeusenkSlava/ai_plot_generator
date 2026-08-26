from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.novels.services.composition import NovelCompositionService
from src.core.novels.services.crud import NovelService
from src.core.novels.services.generate import NovelGenerator
from src.outbound.ai.deepseek_client import DeepSeekNovelGenerator
from src.outbound.ai.dependencies import get_deepseek_generator
from src.outbound.database.dependencies import get_db_session
from src.outbound.database.repositories.novel_repository import NovelRepository


def get_novel_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NovelRepository:
    return NovelRepository(session)


def get_novel_service(
    repository: Annotated[NovelRepository, Depends(get_novel_repository)],
) -> NovelService:
    return NovelService(repository)


def get_novel_generator(
    novel_service: Annotated[NovelService, Depends(get_novel_service)],
    generator: Annotated[DeepSeekNovelGenerator, Depends(get_deepseek_generator)],
) -> NovelGenerator:
    return NovelGenerator(generator=generator, novel_service=novel_service)


def get_novel_composition_service(
    novel_generator: Annotated[NovelGenerator, Depends(get_novel_generator)],
) -> NovelCompositionService:
    return NovelCompositionService(novel_generator=novel_generator)
