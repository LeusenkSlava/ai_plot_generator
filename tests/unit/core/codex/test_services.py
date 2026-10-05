from unittest.mock import AsyncMock

import pytest

from src.core.codex.services import CodexService
from tests.factories import (
    background_domain,
    character_domain,
    universe_domain,
)


@pytest.fixture
def client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sut(client) -> CodexService:
    return CodexService(client)


class TestCodexService:
    async def test_get_universe_delegates(self, sut, client):
        client.get_universe.return_value = universe_domain(id=1)

        result = await sut.get_universe(1)

        client.get_universe.assert_awaited_once_with(universe_id=1)
        assert result == universe_domain(id=1)

    async def test_get_universe_returns_none(self, sut, client):
        client.get_universe.return_value = None

        assert await sut.get_universe(999) is None
        client.get_universe.assert_awaited_once_with(universe_id=999)

    async def test_get_characters_delegates(self, sut, client):
        client.get_characters.return_value = [character_domain(id=1)]

        result = await sut.get_characters(1)

        client.get_characters.assert_awaited_once_with(1)
        assert result == [character_domain(id=1)]

    async def test_get_backgrounds_delegates(self, sut, client):
        client.get_backgrounds.return_value = [background_domain(id=1)]

        result = await sut.get_backgrounds(1)

        client.get_backgrounds.assert_awaited_once_with(1)
        assert result == [background_domain(id=1)]

    async def test_get_sprites_delegates(self, sut, client):
        client.get_sprites.return_value = []

        await sut.get_sprites(character_id=7)

        client.get_sprites.assert_awaited_once_with(7)

    async def test_get_emotions_delegates(self, sut, client):
        client.get_emotions.return_value = []

        await sut.get_emotions(character_id=7)

        client.get_emotions.assert_awaited_once_with(7)

    async def test_get_outfits_delegates(self, sut, client):
        client.get_outfits.return_value = []

        await sut.get_outfits(sprite_id=3)

        client.get_outfits.assert_awaited_once_with(3)

    async def test_client_error_propagates(self, sut, client):
        client.get_universe.side_effect = RuntimeError("http 500")

        with pytest.raises(RuntimeError, match="http 500"):
            await sut.get_universe(1)
