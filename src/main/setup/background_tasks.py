import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class BackgroundTaskRunner:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def start_all(self, factories: dict[str, Callable[[], Awaitable[None]]]) -> None:
        for name, factory in factories.items():
            self._tasks[name] = asyncio.create_task(factory(), name=name)

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        results = await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        for name, result in zip(self._tasks, results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.error("Фоновая задача %s упала", name, exc_info=result)
        self._tasks.clear()
