from src.core.codex.interfaces import CodexClientProtocol
from src.core.codex.models import (
    Background,
    CodexCharacter,
    Emotion,
    Outfit,
    Sprite,
    Universe,
)


class CodexService:
    def __init__(self, client: CodexClientProtocol):
        self._client = client

    async def get_universes(self) -> list[Universe]:
        return await self._client.get_universes()

    async def get_characters(self, universe_id: int) -> list[CodexCharacter]:
        return await self._client.get_characters(universe_id)

    async def get_backgrounds(self, universe_id: int) -> list[Background]:
        return await self._client.get_backgrounds(universe_id)

    async def get_sprites(self, character_id: int) -> list[Sprite]:
        return await self._client.get_sprites(character_id)

    async def get_emotions(self, character_id: int) -> list[Emotion]:
        return await self._client.get_emotions(character_id)

    async def get_outfits(self, sprite_id: int) -> list[Outfit]:
        return await self._client.get_outfits(sprite_id)
