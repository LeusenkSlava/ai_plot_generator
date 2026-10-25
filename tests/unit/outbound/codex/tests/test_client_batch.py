import httpx
import pytest
import respx

from src.core.codex.models import TagType
from src.outbound.codex.codex_client import HttpCodexClient
from tests.unit.outbound.codex.constants import BASE_URL
from tests.unit.outbound.codex.factories import (
    emotion_domain,
    emotion_payload,
    emotion_tag_payload,
    outfit_catalog_payload,
    outfit_domain,
    outfit_style_tag_payload,
    outfit_with_emotions_domain,
    tag_domain,
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
                            id=301,
                            sprite_id=201,
                            slug="coat",
                            name="Пальто",
                            asset_key="outfits/coat.png",
                            tags=[
                                outfit_style_tag_payload(
                                    id=20, slug="coat", name="Пальто"
                                )
                            ],
                            emotions=[
                                emotion_payload(
                                    id=400,
                                    sprite_id=201,
                                    slug="happy",
                                    name="Happy",
                                    asset_key="emotions/happy.png",
                                    tags=[
                                        emotion_tag_payload(
                                            id=30, slug="happy", name="Happy"
                                        )
                                    ],
                                )
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
                    outfit=outfit_domain(
                        id=301,
                        sprite_id=201,
                        slug="coat",
                        name="Пальто",
                        asset_key="outfits/coat.png",
                        tags=[
                            tag_domain(
                                id=20,
                                type=TagType.OUTFIT_STYLE,
                                slug="coat",
                                name="Пальто",
                            )
                        ],
                    ),
                    emotions=[
                        emotion_domain(
                            id=400,
                            sprite_id=201,
                            slug="happy",
                            name="Happy",
                            asset_key="emotions/happy.png",
                            tags=[
                                tag_domain(
                                    id=30,
                                    type=TagType.EMOTION,
                                    slug="happy",
                                    name="Happy",
                                )
                            ],
                        )
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
                json={"201": [outfit_catalog_payload(id=301, sprite_id=201)]},
            )
        )
        sut = HttpCodexClient(client=_http_client, cache=cache)

        first = await sut.get_outfits_with_emotions_batch([201])
        second = await sut.get_outfits_with_emotions_batch([201])

        expected = {
            201: [
                outfit_with_emotions_domain(
                    outfit=outfit_domain(id=301, sprite_id=201)
                )
            ]
        }
        assert first == second == expected
        assert route.call_count == 1
