import json

import httpx
import pytest
import respx

from src.core.codex.exceptions import CodexUnavailableError
from src.core.codex.models import (
    Background,
    CodexCharacter,
    Tag,
    Universe,
    VisualMatch,
)
from tests.unit.outbound.codex.factories import (
    background_domain,
    background_payload,
    character_domain,
    character_payload,
    tag_domain,
    tag_payload,
    universe_domain,
    universe_payload,
)
from tests.unit.outbound.codex.helpers import (
    mock_get_json,
    mock_get_raw,
    mock_get_status,
)
from tests.unit.outbound.codex.routes import (
    backgrounds_url,
    characters_url,
    universe_url,
    visuals_match_url,
)

# ---------------------------------------------------------------------------
# Параметризация list-эндпоинтов
# ---------------------------------------------------------------------------

LIST_ENDPOINTS = [
    pytest.param(
        characters_url,
        character_payload,
        character_domain,
        CodexCharacter,
        lambda sut: sut.get_characters(universe_id=1),
        id="characters",
    ),
    pytest.param(
        backgrounds_url,
        background_payload,
        background_domain,
        Background,
        lambda sut: sut.get_backgrounds(universe_id=1),
        id="backgrounds",
    ),
]


# ---------------------------------------------------------------------------
# get_universe — одиночный объект
# ---------------------------------------------------------------------------


class TestGetUniverse:
    @respx.mock
    async def test_returns_full_domain_model(self, sut):
        mock_get_json(universe_url(1), universe_payload(id=1, title="Мир Тьмы"))

        result = await sut.get_universe(universe_id=1)

        assert result == universe_domain(id=1, title="Мир Тьмы")

    @respx.mock
    async def test_calls_endpoint_once(self, sut):
        route = mock_get_json(universe_url(1), universe_payload())

        await sut.get_universe(universe_id=1)

        assert route.call_count == 1
        assert route.calls.last.request.method == "GET"

    @respx.mock
    async def test_unknown_universe_raises(self, sut):
        mock_get_status(universe_url(999), 404)

        with pytest.raises(CodexUnavailableError, match="Codex request failed"):
            await sut.get_universe(universe_id=999)


# ---------------------------------------------------------------------------
# match_visual — подбор визуала (спрайт + наряд + эмоция)
# ---------------------------------------------------------------------------


class TestMatchVisual:
    @respx.mock
    async def test_returns_visual_match(self, sut):
        respx.post(visuals_match_url(1)).mock(
            return_value=httpx.Response(
                200,
                json={
                    "sprite_asset_key": "sprites/alice.png",
                    "outfit_asset_key": "outfits/red-dress.png",
                    "emotion_asset_key": "emotions/alice-angry.png",
                },
            )
        )

        result = await sut.match_visual(1, "red-dress", ["angry", "soft"])

        assert result == VisualMatch(
            sprite_asset_key="sprites/alice.png",
            outfit_asset_key="outfits/red-dress.png",
            emotion_asset_key="emotions/alice-angry.png",
        )

    @respx.mock
    async def test_null_emotion_asset_key(self, sut):
        respx.post(visuals_match_url(1)).mock(
            return_value=httpx.Response(
                200,
                json={
                    "sprite_asset_key": "sprites/alice.png",
                    "outfit_asset_key": "outfits/red-dress.png",
                    "emotion_asset_key": None,
                },
            )
        )

        result = await sut.match_visual(1, "red-dress", ["unknown"])

        assert result == VisualMatch(
            sprite_asset_key="sprites/alice.png",
            outfit_asset_key="outfits/red-dress.png",
            emotion_asset_key=None,
        )

    @respx.mock
    async def test_sends_request_body(self, sut):
        route = respx.post(visuals_match_url(1)).mock(
            return_value=httpx.Response(
                200,
                json={
                    "sprite_asset_key": "sprites/alice.png",
                    "outfit_asset_key": "outfits/red-dress.png",
                    "emotion_asset_key": None,
                },
            )
        )

        await sut.match_visual(1, "red-dress", ["angry"])

        assert route.call_count == 1
        assert route.calls.last.request.method == "POST"
        assert json.loads(route.calls.last.request.content) == {
            "outfit_tag": "red-dress",
            "emotion_tags": ["angry"],
        }

    @respx.mock
    async def test_404_returns_none(self, sut):
        respx.post(visuals_match_url(1)).mock(return_value=httpx.Response(404))

        assert await sut.match_visual(1, "red-dress", []) is None


# ---------------------------------------------------------------------------
# list-эндпоинты — общие сценарии через параметризацию
# ---------------------------------------------------------------------------


class TestListEndpoints:
    @pytest.mark.parametrize(
        "url_fn,payload_fn,domain_fn,domain_cls,call", LIST_ENDPOINTS
    )
    @respx.mock
    async def test_returns_full_domain_models(
        self, sut, url_fn, payload_fn, domain_fn, domain_cls, call
    ):
        mock_get_json(url_fn(1), [payload_fn(id=1), payload_fn(id=2)])

        result = await call(sut)

        assert result == [domain_fn(id=1), domain_fn(id=2)]
        assert all(isinstance(x, domain_cls) for x in result)

    @pytest.mark.parametrize(
        "url_fn,payload_fn,domain_fn,domain_cls,call", LIST_ENDPOINTS
    )
    @respx.mock
    async def test_empty_list(
        self, sut, url_fn, payload_fn, domain_fn, domain_cls, call
    ):
        mock_get_json(url_fn(1), [])

        assert await call(sut) == []

    @pytest.mark.parametrize(
        "url_fn,payload_fn,domain_fn,domain_cls,call", LIST_ENDPOINTS
    )
    @respx.mock
    async def test_tags_mapped_to_domain(
        self, sut, url_fn, payload_fn, domain_fn, domain_cls, call
    ):
        mock_get_json(
            url_fn(1),
            [payload_fn(tags=[tag_payload(id=1, slug="dark", name="Dark")])],
        )

        result = await call(sut)

        assert result[0].tags == [tag_domain(id=1, slug="dark", name="Dark")]
        assert all(isinstance(t, Tag) for t in result[0].tags)


# ---------------------------------------------------------------------------
# Обработка ошибок — параметризация по типу ошибки и по эндпоинту
# ---------------------------------------------------------------------------

ALL_ENDPOINTS = [
    pytest.param(
        universe_url,
        universe_payload,
        universe_domain,
        Universe,
        lambda sut: sut.get_universe(universe_id=1),
        id="universe",
    ),
    *LIST_ENDPOINTS,
]


ERROR_RESPONSES = [
    pytest.param(
        lambda url: mock_get_status(url, 404),
        id="404",
    ),
    pytest.param(
        lambda url: mock_get_status(url, 500, "boom"),
        id="500",
    ),
    pytest.param(
        lambda url: mock_get_status(url, 503),
        id="503",
    ),
    pytest.param(
        lambda url: mock_get_raw(url, "not json"),
        id="invalid_json",
    ),
    pytest.param(
        lambda url: mock_get_json(url, {"id": 1}),  # не хватает обязательных полей
        id="schema_mismatch",
    ),
]


class TestErrors:
    @pytest.mark.parametrize(
        "url_fn,payload_fn,domain_fn,domain_cls,call", ALL_ENDPOINTS
    )
    @pytest.mark.parametrize("mock_response", ERROR_RESPONSES)
    @respx.mock
    async def test_wrapped_in_codex_unavailable(
        self, sut, url_fn, payload_fn, domain_fn, domain_cls, call, mock_response
    ):
        mock_response(url_fn(1))

        with pytest.raises(CodexUnavailableError, match="Codex request failed"):
            await call(sut)
