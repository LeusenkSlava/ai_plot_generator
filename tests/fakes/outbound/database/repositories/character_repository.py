import dataclasses

from src.core.novels.models import Character


class FakeCharacterRepository:
    def __init__(self) -> None:
        self._items: dict[int, Character] = {}
        self._next_id = 1

    async def add(self, character: Character) -> Character:
        character_id = self._next_id
        self._next_id += 1
        stored = dataclasses.replace(character, id=character_id)
        self._items[character_id] = stored
        return stored

    async def get_by_id(self, character_id: int) -> Character | None:
        return self._items.get(character_id)

    async def list_by_novel_id(self, novel_id: int) -> list[Character]:
        return sorted(
            (c for c in self._items.values() if c.novel_id == novel_id),
            key=lambda c: c.id or 0,
        )

    async def delete(self, character_id: int) -> None:
        self._items.pop(character_id, None)

    @property
    def saved(self) -> list[Character]:
        return list(self._items.values())
