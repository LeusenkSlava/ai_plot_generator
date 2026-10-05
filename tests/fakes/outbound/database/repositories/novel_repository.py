import dataclasses

from src.core.novels.models import Novel


class FakeNovelRepository:
    def __init__(self) -> None:
        self._items: dict[int, Novel] = {}
        self._next_id = 1

    async def add(self, novel: Novel) -> Novel:
        novel_id = self._next_id
        self._next_id += 1
        stored = dataclasses.replace(novel, id=novel_id)
        self._items[novel_id] = stored
        return stored

    async def get_by_id(self, novel_id: int) -> Novel | None:
        return self._items.get(novel_id)

    async def list_all(self, limit: int, offset: int) -> list[Novel]:
        ordered = sorted(
            self._items.values(),
            key=lambda n: (n.created_at or 0, n.id or 0),
            reverse=True,
        )
        return ordered[offset : offset + limit]

    async def count(self) -> int:
        return len(self._items)

    async def delete(self, novel_id: int) -> None:
        self._items.pop(novel_id, None)

    @property
    def saved(self) -> list[Novel]:
        return list(self._items.values())
