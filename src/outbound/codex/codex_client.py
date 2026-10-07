import logging
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from src.core.codex.exceptions import CodexUnavailableError
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
from src.outbound.codex.schemas import (
    BackgroundSchema,
    CharacterSchema,
    EmotionMatchItemSchema,
    EmotionSchema,
    EmotionTagsRequest,
    EmotionTagsResponse,
    OutfitMatchRequest,
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

    async def _request(self, url: str) -> Any:
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"HttpCodexClient GET {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e

    async def _post(self, url: str, payload: Any) -> Any:
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e

    async def _get_one[T](self, url: str, schema: type[T]) -> T:
        data = await self._request(url)
        try:
            return schema.model_validate(data)
        except ValidationError as e:
            logger.error(f"HttpCodexClient GET {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e

    async def _get[T](self, url: str, schema: type[T]) -> list[T]:
        data = await self._request(url)
        try:
            return TypeAdapter(list[schema]).validate_python(data)
        except ValidationError as e:
            logger.error(f"HttpCodexClient GET {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e

    async def _post_one_or_none(
        self, url: str, payload: Any, schema: type, model: type
    ) -> Any:
        """POST с валидацией одиночного объекта; 404 -> None."""
        try:
            response = await self._client.post(url, json=payload)
        except httpx.HTTPError as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        try:
            item = schema.model_validate(data)
        except ValidationError as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        return self._to_domain(item, model)

    @staticmethod
    def _to_domain(item: Any, model: type) -> Any:
        data = (
            item.model_dump(exclude={"tags"})
            if hasattr(item, "tags")
            else item.model_dump()
        )
        if hasattr(item, "tags"):
            data["tags"] = _tags(item.tags)
        return model(**data)

    async def list_universes(self) -> list[Universe]:
        items = await self._get("/universes", UniverseSchema)
        return [self._to_domain(i, Universe) for i in items]

    async def get_universe(self, universe_id: int) -> Universe:
        item = await self._get_one(f"/universes/{universe_id}", UniverseSchema)
        return self._to_domain(item, Universe)

    async def get_characters(self, universe_id: int) -> list[CodexCharacter]:
        items = await self._get(f"/universes/{universe_id}/characters", CharacterSchema)
        return [self._to_domain(i, CodexCharacter) for i in items]

    async def get_backgrounds(self, universe_id: int) -> list[Background]:
        items = await self._get(
            f"/universes/{universe_id}/backgrounds", BackgroundSchema
        )
        return [self._to_domain(i, Background) for i in items]

    async def get_sprites(self, character_id: int) -> list[Sprite]:
        items = await self._get(f"/characters/{character_id}/sprites", SpriteSchema)
        return [self._to_domain(i, Sprite) for i in items]

    async def get_sprites_batch(
        self, character_ids: list[int]
    ) -> dict[int, list[Sprite]]:
        url = "/characters/sprites/batch"
        data = await self._post(url, character_ids)
        try:
            parsed = TypeAdapter(dict[int, list[SpriteSchema]]).validate_python(data)
        except ValidationError as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        return {
            character_id: [self._to_domain(s, Sprite) for s in sprites]
            for character_id, sprites in parsed.items()
        }

    async def get_emotions(self, character_id: int) -> list[Emotion]:
        items = await self._get(f"/characters/{character_id}/emotions", EmotionSchema)
        return [self._to_domain(i, Emotion) for i in items]

    async def get_emotion_tags(self, character_id: int) -> EmotionTags:
        item = await self._get_one(
            f"/characters/{character_id}/emotions/tags", EmotionTagsResponse
        )
        return EmotionTags(
            base=_tags(item.base),
            modifiers=_tags(item.modifiers),
        )

    async def match_emotion(
        self, character_id: int, tags: list[str], sprite_id: int | None = None
    ) -> Emotion | None:
        url = f"/characters/{character_id}/emotions/match"
        payload = EmotionTagsRequest(sprite_id=sprite_id, tags=tags).model_dump(
            exclude_none=True
        )
        return await self._post_one_or_none(url, payload, EmotionSchema, Emotion)

    async def match_emotions_batch(
        self, items: list[EmotionMatchItem]
    ) -> dict[int, Emotion | None]:
        url = "/characters/emotions/batch"
        payload = [
            EmotionMatchItemSchema(
                character_id=i.character_id, sprite_id=i.sprite_id, tags=i.tags
            ).model_dump(exclude_none=True)
            for i in items
        ]
        data = await self._post(url, payload)
        try:
            parsed = TypeAdapter(dict[int, EmotionSchema | None]).validate_python(data)
        except ValidationError as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        return {
            character_id: self._to_domain(e, Emotion) if e is not None else None
            for character_id, e in parsed.items()
        }

    async def get_outfits(self, sprite_id: int) -> list[Outfit]:
        items = await self._get(f"/sprites/{sprite_id}/outfits", OutfitSchema)
        return [self._to_domain(i, Outfit) for i in items]

    async def get_outfit_tags(self, character_id: int) -> list[Tag]:
        items = await self._get(f"/characters/{character_id}/outfits/tags", TagSchema)
        return _tags(items)

    async def match_outfit(self, sprite_id: int, tag: str) -> Outfit | None:
        url = f"/sprites/{sprite_id}/outfits/match"
        payload = OutfitMatchRequest(tag=tag).model_dump()
        return await self._post_one_or_none(url, payload, OutfitSchema, Outfit)
