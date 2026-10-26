import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class _LockEntry:
    __slots__ = ("lock", "refs")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.refs = 0


class KeyedLocks:
    """Пул блокировок по ключу со счётчиком ссылок.

    Сериализует работу по одному ключу (например ``novel_id``), не мешая
    параллельной работе по разным ключам. Ссылки удаляются при нулевом счётчике,
    поэтому пул не растёт бесконечно с числом новелл.
    """

    def __init__(self) -> None:
        self._locks: dict[int, _LockEntry] = {}

    async def run_exclusive(
        self, key: int, factory: Callable[[], Awaitable[T]]
    ) -> T:
        entry = self._locks.get(key)
        if entry is None:
            entry = self._locks[key] = _LockEntry()
        entry.refs += 1
        try:
            async with entry.lock:
                return await factory()
        finally:
            entry.refs -= 1
            if entry.refs == 0:
                self._locks.pop(key, None)
