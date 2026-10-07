import logging
from abc import ABC

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.llm_trace import llm_step

logger = logging.getLogger(__name__)


class BaseGenerator(ABC):
    def __init__(self, generator: GeneratorProtocol):
        self._generator = generator

    async def _generate(
        self,
        prompt: list[dict],
        think: bool = True,
        reasoning_effort: str | None = None,
    ) -> dict:
        try:
            with llm_step(type(self).__name__):
                return await self._generator.generate(
                    prompt, think=think, reasoning_effort=reasoning_effort
                )
        except Exception as e:
            logger.error(f"{type(self).__name__}.generate: {e}")
            raise GenerationError(f"...: {e}") from e
