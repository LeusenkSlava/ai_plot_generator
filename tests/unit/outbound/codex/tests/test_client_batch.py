import httpx
import pytest
import respx

from src.core.codex.models import TagKind
from src.outbound.codex.codex_client import HttpCodexClient
from tests.unit.outbound.codex.constants import BASE_URL
from tests.unit.outbound.codex.factories import (
    outfit_catalog_payload,
    outfit_emotion_domain,
    outfit_emotion_payload,
    outfit_with_emotions_domain,
)


class InMemoryCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        self.store[key] = value


@pytest.fixture
def cache() -> InMemoryCache:
    return InMemoryCache()


class TestOutfitsWithEmotionsBatch:
    @respx.mock
    async def test_parses_and_maps_domain(self, _http_client):
        url = f"{BASE_URL}/characters/outfits-with-emotions/batch"
        respx.post(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "201": [
                        outfit_catalog_payload(
                            outfit_tag="coat",
                            name="Пальто",
                            emotions=[
                                outfit_emotion_payload(
                                    slug="happy", name="Happy", kind=TagKind.BASE
                                ),
                                outfit_emotion_payload(
                                    slug="tears",
                                    name="Со слезами",
                                    kind=TagKind.MODIFIER,
                                ),
                            ],
                        )
                    ],
                    "202": [],
                },
            )
        )
        sut = HttpCodexClient(client=_http_client)

        result = await sut.get_outfits_with_emotions_batch([202, 201])  # вразнобой

        assert result == {
            201: [
                outfit_with_emotions_domain(
                    outfit_tag="coat",
                    name="Пальто",
                    emotions=[
                        outfit_emotion_domain(
                            slug="happy", name="Happy", kind=TagKind.BASE
                        ),
                        outfit_emotion_domain(
                            slug="tears", name="Со слезами", kind=TagKind.MODIFIER
                        ),
                    ],
                )
            ],
            202: [],
        }


class TestBatchEmptyIds:
    @respx.mock
    async def test_empty_ids_do_not_call_codex(self, _http_client):
        sut = HttpCodexClient(client=_http_client)

        assert await sut.get_outfits_with_emotions_batch([]) == {}


class TestBatchCache:
    @respx.mock
    async def test_batch_is_cached(self, _http_client, cache):
        url = f"{BASE_URL}/characters/outfits-with-emotions/batch"
        route = respx.post(url).mock(
            return_value=httpx.Response(
                200,
                json={"201": [outfit_catalog_payload(outfit_tag="casual", name="Casual")]},
            )
        )
        sut = HttpCodexClient(client=_http_client, cache=cache)

        first = await sut.get_outfits_with_emotions_batch([201])
        second = await sut.get_outfits_with_emotions_batch([201])

        expected = {
            201: [outfit_with_emotions_domain(outfit_tag="casual", name="Casual")]
        }
        assert first == second == expected
        assert route.call_count == 1
