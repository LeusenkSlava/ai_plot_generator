import dataclasses

from src.core.novels.models import Roadmap


class FakeRoadmapRepository:
    def __init__(self) -> None:
        self._items: dict[int, Roadmap] = {}
        self._next_id = 1

    async def add(self, roadmap: Roadmap) -> Roadmap:
        roadmap_id = self._next_id
        self._next_id += 1
        stored = dataclasses.replace(roadmap, id=roadmap_id)
        self._items[roadmap_id] = stored
        return stored

    async def get_by_id(self, roadmap_id: int) -> Roadmap | None:
        return self._items.get(roadmap_id)

    async def list_by_novel_id(self, novel_id: int) -> list[Roadmap]:
        return sorted(
            (r for r in self._items.values() if r.novel_id == novel_id),
            key=lambda r: r.step_id,
        )

    async def delete(self, roadmap_id: int) -> None:
        self._items.pop(roadmap_id, None)

    @property
    def saved(self) -> list[Roadmap]:
        return list(self._items.values())
