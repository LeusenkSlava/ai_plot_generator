from src.core.codex.models import Background, CodexCharacter, Universe


class FakeCodexService:
    def __init__(self) -> None:
        self._universes: dict[int, Universe] = {}
        self._characters: dict[int, list[CodexCharacter]] = {}
        self._backgrounds: dict[int, list[Background]] = {}

        self._raise_on: set[str] = set()
        self.calls: list[tuple[str, int]] = []

    # ---------- настройка сценария ----------

    def add_universe(self, universe: Universe) -> None:
        self._universes[universe.id] = universe

    def add_characters(
        self, universe_id: int, characters: list[CodexCharacter]
    ) -> None:
        self._characters[universe_id] = list(characters)

    def add_backgrounds(self, universe_id: int, backgrounds: list[Background]) -> None:
        self._backgrounds[universe_id] = list(backgrounds)

    def fail_on(self, method: str) -> None:
        """Заставить указанный метод бросить RuntimeError."""
        self._raise_on.add(method)

    def clear(self) -> None:
        """Сбросить данные (полезно в тестах на пустые персонажей/локации)."""
        self._characters.clear()
        self._backgrounds.clear()

    # ---------- API как у CodexService ----------

    async def get_universe(self, universe_id: int) -> Universe | None:
        self.calls.append(("get_universe", universe_id))
        if "get_universe" in self._raise_on:
            raise RuntimeError("codex down")
        return self._universes.get(universe_id)

    async def get_characters(self, universe_id: int) -> list[CodexCharacter]:
        self.calls.append(("get_characters", universe_id))
        if "get_characters" in self._raise_on:
            raise RuntimeError("codex down")
        return list(self._characters.get(universe_id, []))

    async def get_backgrounds(self, universe_id: int) -> list[Background]:
        self.calls.append(("get_backgrounds", universe_id))
        if "get_backgrounds" in self._raise_on:
            raise RuntimeError("codex down")
        return list(self._backgrounds.get(universe_id, []))
