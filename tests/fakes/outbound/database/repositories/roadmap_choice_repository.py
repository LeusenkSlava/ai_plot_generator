import dataclasses

from src.core.novels.models import RoadmapChoice


class FakeRoadmapChoiceRepository:
    """Варианты выбора в памяти; порядок — как в БД: depth шага, затем order."""

    def __init__(self, roadmaps=None) -> None:
        self._items: dict[int, RoadmapChoice] = {}
        self._next_id = 1
        self._roadmaps = roadmaps

    async def add(self, choice: RoadmapChoice) -> RoadmapChoice:
        choice_id = self._next_id
        self._next_id += 1
        stored = dataclasses.replace(choice, id=choice_id)
        self._items[choice_id] = stored
        return stored

    async def get_by_id(self, choice_id: int) -> RoadmapChoice | None:
        return self._items.get(choice_id)

    async def list_by_roadmap_id(self, roadmap_id: int) -> list[RoadmapChoice]:
        return sorted(
            (c for c in self._items.values() if c.roadmap_id == roadmap_id),
            key=lambda c: (c.order, c.id or 0),
        )

    async def list_by_novel_id(self, novel_id: int) -> list[RoadmapChoice]:
        if self._roadmaps is None:
            return sorted(self._items.values(), key=lambda c: (c.order, c.id or 0))
        depth_by_roadmap = {
            r.id: r.depth for r in await self._roadmaps.list_by_novel_id(novel_id)
        }
        return sorted(
            (c for c in self._items.values() if c.roadmap_id in depth_by_roadmap),
            key=lambda c: (depth_by_roadmap[c.roadmap_id], c.order, c.id or 0),
        )

    async def update_next_roadmap(
        self, choice_id: int, next_roadmap_id: int
    ) -> None:
        choice = self._items.get(choice_id)
        if choice is not None:
            self._items[choice_id] = dataclasses.replace(
                choice, next_roadmap_id=next_roadmap_id
            )

    async def delete(self, choice_id: int) -> None:
        self._items.pop(choice_id, None)

    @property
    def saved(self) -> list[RoadmapChoice]:
        return list(self._items.values())
