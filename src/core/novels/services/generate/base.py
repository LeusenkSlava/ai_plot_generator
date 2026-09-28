import logging
from abc import ABC

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces import GeneratorProtocol

logger = logging.getLogger(__name__)


class BaseGenerator(ABC):
    def __init__(self, generator: GeneratorProtocol):
        self._generator = generator

    async def _generate(self, prompt: list[dict]) -> dict:
        try:
            return await self._generator.generate(prompt)
        except Exception as e:
            logger.error(f"{type(self).__name__}.generate: {e}")
            raise GenerationError(str(e))
