from src.core.codex.interfaces import CodexClientProtocol
from src.core.codex.models import (
    Background,
    BackgroundMatchItem,
    BackgroundTags,
    CodexCharacter,
    OutfitWithEmotions,
    Universe,
    VisualMatch,
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

    async def get_background_tags(self, universe_id: int) -> BackgroundTags:
        return await self._client.get_background_tags(universe_id)

    async def match_background(
        self, universe_id: int, tags: list[str]
    ) -> Background | None:
        return await self._client.match_background(universe_id, tags)

    async def match_backgrounds_batch(
        self, items: list[BackgroundMatchItem]
    ) -> dict[int, Background | None]:
        return await self._client.match_backgrounds_batch(items)

    async def get_outfits_with_emotions_batch(
        self, character_ids: list[int]
    ) -> dict[int, list[OutfitWithEmotions]]:
        return await self._client.get_outfits_with_emotions_batch(character_ids)

    async def match_visual(
        self, character_id: int, outfit_tag: str, emotion_tags: list[str]
    ) -> VisualMatch | None:
        return await self._client.match_visual(
            character_id=character_id,
            outfit_tag=outfit_tag,
            emotion_tags=emotion_tags,
        )
