from src.core.novels.models import Novel
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)


class FakeNovelService:
    def __init__(self, repository: FakeNovelRepository | None = None) -> None:
        self._repository = repository or FakeNovelRepository()
        self.raise_on_add: Exception | None = None

    async def add(self, novel: Novel) -> Novel:
        if self.raise_on_add is not None:
            raise self.raise_on_add
        return await self._repository.add(novel)

    async def get(self, novel_id: int) -> Novel | None:
        return await self._repository.get_by_id(novel_id)

    async def list(self, limit: int, offset: int) -> tuple[list[Novel], int]:
        items = await self._repository.list_all(limit=limit, offset=offset)
        total = await self._repository.count()
        return items, total

    async def delete(self, novel_id: int) -> None:
        await self._repository.delete(novel_id)

    # ---------- удобства для тестов ----------

    @property
    def saved(self) -> list[Novel]:
        return self._repository.saved
