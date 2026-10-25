import httpx
import pytest
import respx
from redis.exceptions import RedisError

from src.outbound.cache.redis_cache import RedisCache
from src.outbound.codex.codex_client import HttpCodexClient
from tests.unit.outbound.codex.constants import BASE_URL
from tests.unit.outbound.codex.factories import (
    background_domain,
    background_payload,
    universe_domain,
    universe_payload,
)
from tests.unit.outbound.codex.helpers import mock_get_json
from tests.unit.outbound.codex.routes import universe_url


class InMemoryCache:
    """Минимальная реализация CacheProtocol для тестов."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        self.store[key] = value


@pytest.fixture
def cache() -> InMemoryCache:
    return InMemoryCache()


class TestGetCache:
    @respx.mock
    async def test_serves_second_call_from_cache(self, _http_client, cache):
        route = mock_get_json(universe_url(1), universe_payload(id=1))
        sut = HttpCodexClient(client=_http_client, cache=cache)

        first = await sut.get_universe(universe_id=1)
        second = await sut.get_universe(universe_id=1)

        assert first == universe_domain(id=1)
        assert second == first
        assert route.call_count == 1


class TestMatchCache:
    @respx.mock
    async def test_hit_is_cached(self, _http_client, cache):
        url = f"{BASE_URL}/universes/1/backgrounds/match"
        payload = background_payload(id=7, slug="forest")
        route = respx.post(url).mock(return_value=httpx.Response(200, json=payload))
        sut = HttpCodexClient(client=_http_client, cache=cache)

        first = await sut.match_background(1, ["forest"])
        second = await sut.match_background(1, ["forest"])

        assert first == background_domain(id=7, slug="forest")
        assert second == first
        assert route.call_count == 1

    @respx.mock
    async def test_miss_is_cached(self, _http_client, cache):
        url = f"{BASE_URL}/universes/1/backgrounds/match"
        route = respx.post(url).mock(return_value=httpx.Response(404))
        sut = HttpCodexClient(client=_http_client, cache=cache)

        first = await sut.match_background(1, ["forest"])
        second = await sut.match_background(1, ["forest"])

        assert first is None
        assert second is None
        assert route.call_count == 1


class _BrokenRedis:
    async def get(self, key: str) -> str | None:
        raise RedisError("down")

    async def set(self, key: str, value: str, ex: int) -> None:
        raise RedisError("down")


class TestRedisCacheDegradation:
    async def test_get_returns_none_on_redis_error(self):
        cache = RedisCache(_BrokenRedis())  # type: ignore[arg-type]

        assert await cache.get("k") is None

    async def test_set_is_noop_on_redis_error(self):
        cache = RedisCache(_BrokenRedis())  # type: ignore[arg-type]

        await cache.set("k", "v", 10)  # не должно падать
