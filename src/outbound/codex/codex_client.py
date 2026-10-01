import logging
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from src.core.codex.exceptions import CodexUnavailableError
from src.core.codex.models import (
    Background,
    CodexCharacter,
    Emotion,
    Outfit,
    Sprite,
    Tag,
    Universe,
)
from src.outbound.codex.schemas import (
    BackgroundSchema,
    CharacterSchema,
    EmotionSchema,
    OutfitSchema,
    SpriteSchema,
    TagSchema,
    UniverseSchema,
)

logger = logging.getLogger(__name__)


def _tags(tags: list[TagSchema]) -> list[Tag]:
    return [Tag(**t.model_dump()) for t in tags]


class HttpCodexClient:
    """Реализует CodexClientProtocol поверх HTTP API Codex."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def _get[T](self, url: str, schema: type[T]) -> list[T]:
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return TypeAdapter(list[schema]).validate_python(response.json())
        except (httpx.HTTPError, ValidationError, ValueError) as e:
            logger.error(f"HttpCodexClient GET {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e

    @staticmethod
    def _to_domain(item: Any, model: type) -> Any:
        data = item.model_dump(exclude={"tags"}) if hasattr(item, "tags") else item.model_dump()
        if hasattr(item, "tags"):
            data["tags"] = _tags(item.tags)
        return model(**data)

    async def get_universes(self) -> list[Universe]:
        items = await self._get("/universes", UniverseSchema)
        return [self._to_domain(i, Universe) for i in items]

    async def get_characters(self, universe_id: int) -> list[CodexCharacter]:
        items = await self._get(f"/universes/{universe_id}/characters", CharacterSchema)
        return [self._to_domain(i, CodexCharacter) for i in items]

    async def get_backgrounds(self, universe_id: int) -> list[Background]:
        items = await self._get(f"/universes/{universe_id}/backgrounds", BackgroundSchema)
        return [self._to_domain(i, Background) for i in items]

    async def get_sprites(self, character_id: int) -> list[Sprite]:
        items = await self._get(f"/characters/{character_id}/sprites", SpriteSchema)
        return [self._to_domain(i, Sprite) for i in items]

    async def get_emotions(self, character_id: int) -> list[Emotion]:
        items = await self._get(f"/characters/{character_id}/emotions", EmotionSchema)
        return [self._to_domain(i, Emotion) for i in items]

    async def get_outfits(self, sprite_id: int) -> list[Outfit]:
        items = await self._get(f"/sprites/{sprite_id}/outfits", OutfitSchema)
        return [self._to_domain(i, Outfit) for i in items]
