from sqlalchemy.ext.asyncio import AsyncSession

from src.core.novels.services.composition import NovelCompositionService
from src.core.novels.services.crud import NovelService
from src.core.novels.services.generate import NovelGenerator
from src.outbound.ai.client import build_deepseek_client
from src.outbound.ai.deepseek_client import DeepSeekNovelGenerator
from src.outbound.database.repositories.novel_repository import NovelRepository


def build_novel_composition_service(session: AsyncSession) -> NovelCompositionService:
    repository = NovelRepository(session)
    novel_service = NovelService(repository)
    generator = DeepSeekNovelGenerator(client=build_deepseek_client())
    novel_generator = NovelGenerator(generator=generator, novel_service=novel_service)
    return NovelCompositionService(novel_generator=novel_generator)
