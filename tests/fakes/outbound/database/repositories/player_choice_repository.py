import dataclasses

from src.core.novels.models import PlayerChoice


class FakePlayerChoiceRepository:
    """Журнал выбранных игроком вариантов в памяти."""

    def __init__(self) -> None:
        self._items: dict[int, PlayerChoice] = {}
        self._next_id = 1

    async def add(self, player_choice: PlayerChoice) -> PlayerChoice:
        player_choice_id = self._next_id
        self._next_id += 1
        stored = dataclasses.replace(player_choice, id=player_choice_id)
        self._items[player_choice_id] = stored
        return stored

    async def get_by_id(self, player_choice_id: int) -> PlayerChoice | None:
        return self._items.get(player_choice_id)

    async def list_by_novel_id(self, novel_id: int) -> list[PlayerChoice]:
        return sorted(
            (c for c in self._items.values() if c.novel_id == novel_id),
            key=lambda c: c.id or 0,
        )

    async def get_by_roadmap_choice_id(
        self, roadmap_choice_id: int
    ) -> PlayerChoice | None:
        return next(
            (
                c
                for c in self._items.values()
                if c.roadmap_choice_id == roadmap_choice_id
            ),
            None,
        )

    async def delete(self, player_choice_id: int) -> None:
        self._items.pop(player_choice_id, None)

    @property
    def saved(self) -> list[PlayerChoice]:
        return list(self._items.values())
