from src.core.codex.exceptions import CodexUnavailableError
from src.core.codex.models import (
    Background,
    CodexCharacter,
    Emotion,
    EmotionTags,
    Outfit,
    Sprite,
    Tag,
    Universe,
)


class FakeCodexService:
    """Управляемый Codex: отдаёт засеянные данные и записывает вызовы.

    Покрывает как генератор новеллы (universe/characters/backgrounds), так и
    генератор диалога (sprites/emotion_tags/outfit_tags/outfits и подбор
    match_emotion/match_outfit).
    """

    def __init__(self) -> None:
        self._universes: dict[int, Universe] = {}
        self._characters: dict[int, list[CodexCharacter]] = {}
        self._backgrounds: dict[int, list[Background]] = {}

        self._sprites: dict[int, list[Sprite]] = {}
        self._emotion_tags: dict[int, EmotionTags] = {}
        self._outfit_tags: dict[int, list[Tag]] = {}
        self._outfits: dict[int, list[Outfit]] = {}
        self._emotion_matches: dict[int, Emotion | None] = {}
        self._outfit_matches: dict[int, dict[str, Outfit | None]] = {}

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

    def add_sprites(self, character_id: int, sprites: list[Sprite]) -> None:
        self._sprites[character_id] = list(sprites)

    def add_emotion_tags(self, character_id: int, tags: EmotionTags) -> None:
        self._emotion_tags[character_id] = tags

    def add_outfit_tags(self, character_id: int, tags: list[Tag]) -> None:
        self._outfit_tags[character_id] = list(tags)

    def add_outfits(self, sprite_id: int, outfits: list[Outfit]) -> None:
        self._outfits[sprite_id] = list(outfits)

    def set_match_emotion(self, character_id: int, emotion: Emotion | None) -> None:
        """Эмоция, которую вернёт match_emotion для персонажа (или None)."""
        self._emotion_matches[character_id] = emotion

    def set_match_outfit(
        self, sprite_id: int, tag: str, outfit: Outfit | None
    ) -> None:
        """Наряд, который вернёт match_outfit для (sprite_id, tag)."""
        self._outfit_matches.setdefault(sprite_id, {})[tag] = outfit

    def fail_on(self, method: str) -> None:
        """Заставить указанный метод бросить ошибку.

        match_emotion/match_outfit бросают CodexUnavailableError (как реальный
        клиент), остальные методы — RuntimeError.
        """
        self._raise_on.add(method)

    def clear(self) -> None:
        """Сбросить данные (полезно в тестах на пустые персонажи/локации)."""
        self._characters.clear()
        self._backgrounds.clear()
        self._sprites.clear()
        self._emotion_tags.clear()
        self._outfit_tags.clear()
        self._outfits.clear()
        self._emotion_matches.clear()
        self._outfit_matches.clear()

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

    async def get_sprites(self, character_id: int) -> list[Sprite]:
        self.calls.append(("get_sprites", character_id))
        if "get_sprites" in self._raise_on:
            raise RuntimeError("codex down")
        return list(self._sprites.get(character_id, []))

    async def get_emotion_tags(self, character_id: int) -> EmotionTags:
        self.calls.append(("get_emotion_tags", character_id))
        if "get_emotion_tags" in self._raise_on:
            raise RuntimeError("codex down")
        return self._emotion_tags.get(character_id, EmotionTags())

    async def get_outfit_tags(self, character_id: int) -> list[Tag]:
        self.calls.append(("get_outfit_tags", character_id))
        if "get_outfit_tags" in self._raise_on:
            raise RuntimeError("codex down")
        return list(self._outfit_tags.get(character_id, []))

    async def get_outfits(self, sprite_id: int) -> list[Outfit]:
        self.calls.append(("get_outfits", sprite_id))
        if "get_outfits" in self._raise_on:
            raise RuntimeError("codex down")
        return list(self._outfits.get(sprite_id, []))

    async def match_emotion(
        self, character_id: int, tags: list[str], sprite_id: int | None = None
    ) -> Emotion | None:
        self.calls.append(("match_emotion", character_id, list(tags), sprite_id))
        if "match_emotion" in self._raise_on:
            raise CodexUnavailableError("codex down")
        return self._emotion_matches.get(character_id)

    async def match_outfit(self, sprite_id: int, tag: str) -> Outfit | None:
        self.calls.append(("match_outfit", sprite_id, tag))
        if "match_outfit" in self._raise_on:
            raise CodexUnavailableError("codex down")
        return self._outfit_matches.get(sprite_id, {}).get(tag)
