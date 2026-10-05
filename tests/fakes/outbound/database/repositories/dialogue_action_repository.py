import dataclasses

from src.core.novels.models import DialogueAction


class FakeDialogueActionRepository:
    def __init__(self) -> None:
        self._items: dict[int, DialogueAction] = {}
        self._next_id = 1

    async def add(self, dialog_action: DialogueAction) -> DialogueAction:
        dialog_action_id = self._next_id
        self._next_id += 1
        stored = dataclasses.replace(dialog_action, id=dialog_action_id)
        self._items[dialog_action_id] = stored
        return stored

    async def get_by_id(self, dialog_action_id: int) -> DialogueAction | None:
        return self._items.get(dialog_action_id)

    async def delete(self, dialog_action_id: int) -> None:
        self._items.pop(dialog_action_id, None)

    @property
    def saved(self) -> list[DialogueAction]:
        return list(self._items.values())
