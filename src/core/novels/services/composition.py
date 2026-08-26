import logging

from src.core.novels.models import Novel
from src.core.novels.services.generate import NovelGenerator

logger = logging.getLogger(__name__)


class NovelCompositionService:
    def __init__(
        self,
        novel_generator: NovelGenerator,
    ):
        self._novel_generator = novel_generator

    async def create(self, user_promt: str) -> Novel:
        novel = await self._novel_generator.generate(user_promt)
        return novel
