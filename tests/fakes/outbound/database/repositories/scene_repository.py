import dataclasses

from src.core.novels.models import Scene
from tests.fakes.outbound.database.repositories.roadmap_repository import (
    FakeRoadmapRepository,
)


class FakeSceneRepository:
    def __init__(self, roadmaps: FakeRoadmapRepository | None = None) -> None:
        self._items: dict[int, Scene] = {}
        self._next_id = 1
        self._roadmaps = roadmaps

    async def add(self, scene: Scene) -> Scene:
        scene_id = self._next_id
        self._next_id += 1
        stored = dataclasses.replace(scene, id=scene_id)
        self._items[scene_id] = stored
        return stored

    async def get_by_id(self, scene_id: int) -> Scene | None:
        return self._items.get(scene_id)

    async def list_by_roadmap_id(self, roadmap_id: int) -> list[Scene]:
        return sorted(
            (s for s in self._items.values() if s.roadmap_id == roadmap_id),
            key=lambda s: s.order,
        )

    async def list_by_novel_id(self, novel_id: int) -> list[Scene]:
        """Все сцены новеллы по порядку: шаг роадмапа -> сцена.

        Для упорядочивания нужен доступ к роадмапам — передайте FakeRoadmapRepository
        в конструктор, иначе сцены вернутся в порядке order/id без фильтра по новелле.
        """
        if self._roadmaps is None:
            return sorted(
                self._items.values(),
                key=lambda s: (s.order, s.id or 0),
            )
        step_by_roadmap = {
            r.id: r.step_id for r in await self._roadmaps.list_by_novel_id(novel_id)
        }
        return sorted(
            (s for s in self._items.values() if s.roadmap_id in step_by_roadmap),
            key=lambda s: (step_by_roadmap[s.roadmap_id], s.order, s.id or 0),
        )

    async def update_story_context(self, scene_id: int, story_context: str) -> None:
        scene = self._items.get(scene_id)
        if scene:
            self._items[scene_id] = dataclasses.replace(
                scene, story_context=story_context
            )

    async def delete(self, scene_id: int) -> None:
        self._items.pop(scene_id, None)

    @property
    def saved(self) -> list[Scene]:
        return list(self._items.values())
