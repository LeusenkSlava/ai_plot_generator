from src.core.codex.exceptions import CodexUnavailableError
from src.core.codex.models import (
    Background,
    BackgroundTags,
    CodexCharacter,
    OutfitWithEmotions,
    Universe,
    VisualMatch,
)


class FakeCodexService:
    """Управляемый Codex: отдаёт засеянные данные и записывает вызовы.

    Покрывает как генератор новеллы (universe/characters/backgrounds), так и
    генератор диалога (каталог нарядов с эмоциями и подбор визуала
    match_visual).
    """

    def __init__(self) -> None:
        self._universes: dict[int, Universe] = {}
        self._characters: dict[int, list[CodexCharacter]] = {}
        self._backgrounds: dict[int, list[Background]] = {}
        self._background_tags: dict[int, BackgroundTags] = {}

        self._outfits_with_emotions: dict[int, list[OutfitWithEmotions]] = {}
        self._visual_matches: dict[
            tuple[int, str, tuple[str, ...]], VisualMatch | None
        ] = {}

        self._raise_on: set[str] = set()
        self.calls: list[tuple] = []

    # ---------- настройка сценария ----------

    def add_universe(self, universe: Universe) -> None:
        self._universes[universe.id] = universe

    def add_characters(
        self, universe_id: int, characters: list[CodexCharacter]
    ) -> None:
        self._characters[universe_id] = list(characters)

    def add_backgrounds(self, universe_id: int, backgrounds: list[Background]) -> None:
        self._backgrounds[universe_id] = list(backgrounds)

    def add_background_tags(
        self, universe_id: int, tags: BackgroundTags
    ) -> None:
        self._background_tags[universe_id] = tags

    def add_outfits_with_emotions(
        self, character_id: int, outfits: list[OutfitWithEmotions]
    ) -> None:
        self._outfits_with_emotions[character_id] = list(outfits)

    def set_match_visual(
        self,
        character_id: int,
        outfit_tag: str,
        emotion_tags: list[str],
        visual: VisualMatch | None,
    ) -> None:
        """Визуал, который вернёт match_visual для (character_id, outfit_tag, emotion_tags)."""
        self._visual_matches[(character_id, outfit_tag, tuple(emotion_tags))] = visual

    def fail_on(self, method: str) -> None:
        """Заставить указанный метод бросить ошибку.

        match_visual бросает CodexUnavailableError (как реальный клиент),
        остальные методы — RuntimeError.
        """
        self._raise_on.add(method)

    def clear(self) -> None:
        """Сбросить данные (полезно в тестах на пустые персонажи/локации)."""
        self._characters.clear()
        self._backgrounds.clear()
        self._background_tags.clear()
        self._outfits_with_emotions.clear()
        self._visual_matches.clear()

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

    async def get_background_tags(self, universe_id: int) -> BackgroundTags:
        self.calls.append(("get_background_tags", universe_id))
        if "get_background_tags" in self._raise_on:
            raise RuntimeError("codex down")
        return self._background_tags.get(universe_id, BackgroundTags())

    async def match_background(
        self, universe_id: int, tags: list[str]
    ) -> Background | None:
        """Подбор задника по slug в тегах (как реальный CodexService)."""
        self.calls.append(("match_background", universe_id, list(tags)))
        if "match_background" in self._raise_on:
            raise CodexUnavailableError("codex down")
        for background in self._backgrounds.get(universe_id, []):
            if background.slug in tags:
                return background
        return None

    async def get_outfits_with_emotions_batch(
        self, character_ids: list[int]
    ) -> dict[int, list[OutfitWithEmotions]]:
        self.calls.append(("get_outfits_with_emotions_batch", sorted(character_ids)))
        if "get_outfits_with_emotions_batch" in self._raise_on:
            raise RuntimeError("codex down")
        return {
            character_id: list(self._outfits_with_emotions.get(character_id, []))
            for character_id in character_ids
        }

    async def match_visual(
        self, character_id: int, outfit_tag: str, emotion_tags: list[str]
    ) -> VisualMatch | None:
        self.calls.append(
            ("match_visual", character_id, outfit_tag, list(emotion_tags))
        )
        if "match_visual" in self._raise_on:
            raise CodexUnavailableError("codex down")
        return self._visual_matches.get(
            (character_id, outfit_tag, tuple(emotion_tags))
        )
