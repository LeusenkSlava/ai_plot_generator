from src.core.codex.interfaces import CodexClientProtocol
from src.core.codex.models import (
    Background,
    CodexCharacter,
    Emotion,
    EmotionMatchItem,
    EmotionTags,
    Outfit,
    Sprite,
    Tag,
    Universe,
)


class CodexService:
    def __init__(self, client: CodexClientProtocol):
        self._client = client

    async def list_universes(self) -> list[Universe]:
        return await self._client.list_universes()

    async def get_universe(self, universe_id: int) -> Universe:
        return await self._client.get_universe(universe_id=universe_id)

    async def get_characters(self, universe_id: int) -> list[CodexCharacter]:
        return await self._client.get_characters(universe_id)

    async def get_backgrounds(self, universe_id: int) -> list[Background]:
        return await self._client.get_backgrounds(universe_id)

    async def get_sprites(self, character_id: int) -> list[Sprite]:
        return await self._client.get_sprites(character_id)

    async def get_sprites_batch(
        self, character_ids: list[int]
    ) -> dict[int, list[Sprite]]:
        return await self._client.get_sprites_batch(character_ids)

    async def get_emotions(self, character_id: int) -> list[Emotion]:
        return await self._client.get_emotions(character_id)

    async def get_emotion_tags(self, character_id: int) -> EmotionTags:
        return await self._client.get_emotion_tags(character_id)

    async def match_emotion(
        self, character_id: int, tags: list[str], sprite_id: int | None = None
    ) -> Emotion | None:
        return await self._client.match_emotion(
            character_id=character_id, tags=tags, sprite_id=sprite_id
        )

    async def match_emotions_batch(
        self, items: list[EmotionMatchItem]
    ) -> dict[int, Emotion | None]:
        return await self._client.match_emotions_batch(items)

    async def get_outfits(self, sprite_id: int) -> list[Outfit]:
        return await self._client.get_outfits(sprite_id)

    async def get_outfit_tags(self, character_id: int) -> list[Tag]:
        return await self._client.get_outfit_tags(character_id)

    async def match_outfit(self, sprite_id: int, tag: str) -> Outfit | None:
        return await self._client.match_outfit(sprite_id, tag)
