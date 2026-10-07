import dataclasses

from src.core.novels.models import DialogueLine


class FakeDialogueLineRepository:
    def __init__(self) -> None:
        self._items: dict[int, DialogueLine] = {}
        self._next_id = 1
        self._last_outfits: dict[int, str] = {}

    def set_last_outfits(self, mapping: dict[int, str]) -> None:
        """Явно задать последний наряд по персонажу (character_id -> asset_key)."""
        self._last_outfits = dict(mapping)

    async def add(self, dialog_line: DialogueLine) -> DialogueLine:
        dialog_line_id = self._next_id
        self._next_id += 1
        stored = dataclasses.replace(dialog_line, id=dialog_line_id)
        self._items[dialog_line_id] = stored
        return stored

    async def get_by_id(self, dialog_line_id: int) -> DialogueLine | None:
        return self._items.get(dialog_line_id)

    async def list_by_novel_id(self, novel_id: int) -> list[DialogueLine]:
        return sorted(
            (l for l in self._items.values() if l.novel_id == novel_id),
            key=lambda l: (l.order, l.id or 0),
        )

    async def list_by_scene_id(self, scene_id: int) -> list[DialogueLine]:
        return sorted(
            (l for l in self._items.values() if l.scene_id == scene_id),
            key=lambda l: l.order,
        )

    async def last_outfit_per_character(self, novel_id: int) -> dict[int, str]:
        if self._last_outfits:
            return dict(self._last_outfits)
        result: dict[int, str] = {}
        for line in self._items.values():
            if line.novel_id == novel_id and line.outfit_asset_key is not None:
                result[line.character_id] = line.outfit_asset_key
        return result

    async def delete(self, dialog_line_id: int) -> None:
        self._items.pop(dialog_line_id, None)

    @property
    def saved(self) -> list[DialogueLine]:
        return list(self._items.values())
