import hashlib
import json
import logging
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from src.core.codex.exceptions import CodexUnavailableError
from src.core.codex.models import (
    Background,
    BackgroundMatchItem,
    BackgroundTags,
    CodexCharacter,
    Emotion,
    Outfit,
    OutfitWithEmotions,
    Tag,
    Universe,
    VisualMatch,
)
from src.outbound.cache.redis_cache import CacheProtocol
from src.outbound.codex.schemas import (
    BackgroundMatchItemSchema,
    BackgroundSchema,
    BackgroundTagsRequest,
    BackgroundTagsResponse,
    CharacterSchema,
    OutfitCatalogSchema,
    TagSchema,
    UniverseSchema,
    VisualMatchRequest,
    VisualMatchResponse,
)

logger = logging.getLogger(__name__)

_CACHE_MISS = "__NONE__"


def _cache_key(verb: str, url: str, payload: Any = None) -> str:
    """Ключ кэша: verb + URL (+ хэш тела для POST-запросов подбора)."""
    key = f"codex:{verb}:{url}"
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        key += f":{hashlib.sha256(body.encode()).hexdigest()}"
    return key


def _batch_cache_key(resource: str, ids: list[int]) -> str:
    """Ключ кэша для батча: не зависит от порядка id в запросе."""
    return f"codex:batch:{resource}:" + ",".join(str(i) for i in sorted(ids))


def _tags(tags: list[TagSchema]) -> list[Tag]:
    return [Tag(**t.model_dump()) for t in tags]


def _outfit_from_catalog(entry: OutfitCatalogSchema) -> Outfit:
    """Превращает элемент каталога нарядов в доменный Outfit (без вложенных эмоций)."""
    data = entry.model_dump(exclude={"tags", "emotions"})
    data["tags"] = _tags(entry.tags)
    return Outfit(**data)


class HttpCodexClient:
    """Реализует CodexClientProtocol поверх HTTP API Codex.

    Кэширует сырой JSON ответов в Redis (необязательно): справочные GET-методы —
    с ``get_ttl_s``, детерминированные match_* — с ``match_ttl_s`` (включая
    известные «нет совпадения»). При недоступности кэша прозрачно ходим в Codex.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        cache: CacheProtocol | None = None,
        *,
        get_ttl_s: int = 1800,
        match_ttl_s: int = 300,
    ):
        self._client = client
        self._cache = cache
        self._get_ttl_s = get_ttl_s
        self._match_ttl_s = match_ttl_s

    async def _request(self, url: str) -> Any:
        key = _cache_key("get", url)
        if self._cache is not None:
            cached = await self._cache.get(key)
            if cached is not None:
                return json.loads(cached)
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"HttpCodexClient GET {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        if self._cache is not None:
            await self._cache.set(
                key, json.dumps(data, ensure_ascii=False), self._get_ttl_s
            )
        return data

    async def _post(self, url: str, payload: Any) -> Any:
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e

    async def _post_cached(
        self, url: str, payload: Any, cache_key: str, ttl_s: int
    ) -> Any:
        """POST с кэшем сырого JSON (для детерминированных батчей)."""
        if self._cache is not None:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return json.loads(cached)
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        if self._cache is not None:
            await self._cache.set(
                cache_key, json.dumps(data, ensure_ascii=False), ttl_s
            )
        return data

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
        """POST с валидацией одиночного объекта; 404 -> None.

        Ответ и «отсутствие ответа» (404) кэшируются: результат подбора
        детерминирован для одних и тех же входных тегов.
        """
        key = _cache_key("post", url, payload)
        if self._cache is not None:
            cached = await self._cache.get(key)
            if cached is not None:
                if cached == _CACHE_MISS:
                    return None
                try:
                    item = schema.model_validate(json.loads(cached))
                except (ValidationError, ValueError) as e:
                    logger.error(f"HttpCodexClient cached POST {url}: {e}")
                else:
                    return self._to_domain(item, model)
        try:
            response = await self._client.post(url, json=payload)
        except httpx.HTTPError as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        if response.status_code == 404:
            if self._cache is not None:
                await self._cache.set(key, _CACHE_MISS, self._match_ttl_s)
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
        if self._cache is not None:
            await self._cache.set(
                key, json.dumps(data, ensure_ascii=False), self._match_ttl_s
            )
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

    async def get_background_tags(self, universe_id: int) -> BackgroundTags:
        item = await self._get_one(
            f"/universes/{universe_id}/backgrounds/tags", BackgroundTagsResponse
        )
        return BackgroundTags(base=_tags(item.base), modifiers=_tags(item.modifiers))

    async def match_background(
        self, universe_id: int, tags: list[str]
    ) -> Background | None:
        url = f"/universes/{universe_id}/backgrounds/match"
        payload = BackgroundTagsRequest(tags=tags).model_dump()
        return await self._post_one_or_none(url, payload, BackgroundSchema, Background)

    async def match_backgrounds_batch(
        self, items: list[BackgroundMatchItem]
    ) -> dict[int, Background | None]:
        url = "/universes/backgrounds/batch"
        payload = [
            BackgroundMatchItemSchema(
                universe_id=i.universe_id, tags=i.tags
            ).model_dump()
            for i in items
        ]
        data = await self._post(url, payload)
        try:
            parsed = TypeAdapter(dict[int, BackgroundSchema | None]).validate_python(
                data
            )
        except ValidationError as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        return {
            universe_id: self._to_domain(b, Background) if b is not None else None
            for universe_id, b in parsed.items()
        }

    async def get_outfits_with_emotions_batch(
        self, character_ids: list[int]
    ) -> dict[int, list[OutfitWithEmotions]]:
        url = "/characters/outfits-with-emotions/batch"
        ids = sorted(character_ids)
        if not ids:
            return {}
        data = await self._post_cached(
            url, ids, _batch_cache_key("outfits_with_emotions", ids), self._get_ttl_s
        )
        try:
            parsed = TypeAdapter(
                dict[int, list[OutfitCatalogSchema]]
            ).validate_python(data)
        except ValidationError as e:
            logger.error(f"HttpCodexClient POST {url}: {e}")
            raise CodexUnavailableError(f"Codex request failed: {url}: {e}") from e
        return {
            character_id: [
                OutfitWithEmotions(
                    outfit=_outfit_from_catalog(entry),
                    emotions=[self._to_domain(e, Emotion) for e in entry.emotions],
                )
                for entry in entries
            ]
            for character_id, entries in parsed.items()
        }

    async def match_visual(
        self, character_id: int, outfit_tag: str, emotion_tags: list[str]
    ) -> VisualMatch | None:
        url = f"/characters/{character_id}/visuals/match"
        payload = VisualMatchRequest(
            outfit_tag=outfit_tag, emotion_tags=emotion_tags
        ).model_dump()
        return await self._post_one_or_none(
            url, payload, VisualMatchResponse, VisualMatch
        )
