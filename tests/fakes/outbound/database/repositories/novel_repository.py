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

    async def get_by_id(
        self, novel_id: int, author_id: int | None = None
    ) -> Novel | None:
        novel = self._items.get(novel_id)
        if novel is None:
            return None
        if author_id is not None and novel.author_id != author_id:
            return None
        return novel

    async def list_all(
        self, limit: int, offset: int, author_id: int | None = None
    ) -> list[Novel]:
        items = self._items.values()
        if author_id is not None:
            items = [n for n in items if n.author_id == author_id]
        ordered = sorted(
            items,
            key=lambda n: (n.created_at or 0, n.id or 0),
            reverse=True,
        )
        return ordered[offset : offset + limit]

    async def count(self, author_id: int | None = None) -> int:
        if author_id is None:
            return len(self._items)
        return sum(1 for n in self._items.values() if n.author_id == author_id)

    async def delete(self, novel_id: int, author_id: int | None = None) -> bool:
        novel = self._items.get(novel_id)
        if novel is None:
            return False
        if author_id is not None and novel.author_id != author_id:
            return False
        self._items.pop(novel_id, None)
        return True

    async def update_plot_design(self, novel_id: int, plot_design: dict) -> None:
        novel = self._items.get(novel_id)
        if novel is not None:
            self._items[novel_id] = dataclasses.replace(
                novel, plot_design=plot_design
            )

    @property
    def saved(self) -> list[Novel]:
        return list(self._items.values())
