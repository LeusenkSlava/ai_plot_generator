"""Юнит-тесты SceneAssetService: резолв ассетов сцены через Codex."""

from src.core.novels.services.generation.assets import (
    LineAssets,
    SceneAssets,
    SceneAssetService,
)
from tests.factories import background_domain, novel_character_domain
from tests.fakes.outbound.codex.client import FakeCodexService


async def test_match_assets_propagates_sound_asset_key():
    """sound_asset_key из Background доезжает до ResolvedAssets."""
    codex = FakeCodexService()
    codex.add_backgrounds(
        1,
        [
            background_domain(
                id=1,
                universe_id=1,
                slug="forest",
                description="Лес",
                asset_key="bg/forest.png",
                sound_asset_key="sounds/forest.ogg",
            )
        ],
    )

    service = SceneAssetService(codex)
    # Протагонист: визуал не подбирается, резолвится только фон.
    character = novel_character_domain(
        id=1, novel_id=1, name="Алиса", role="Ведьма", is_protagonist=True,
    )
    prepared = [(character, {}, LineAssets(background_tags=["forest"]))]

    resolved = await service.match_assets(prepared, SceneAssets(), universe_id=1)

    assert resolved[0].background_asset_key == "bg/forest.png"
    assert resolved[0].sound_asset_key == "sounds/forest.ogg"


async def test_match_assets_sound_asset_key_none_when_missing():
    """Если у Background нет sound_asset_key — в ResolvedAssets лежит None."""
    codex = FakeCodexService()
    codex.add_backgrounds(
        1,
        [
            background_domain(
                id=1, universe_id=1, slug="forest", description="Лес",
                asset_key="bg/forest.png",
            )
        ],
    )

    service = SceneAssetService(codex)
    character = novel_character_domain(
        id=1, novel_id=1, name="Алиса", role="Ведьма", is_protagonist=True,
    )
    prepared = [(character, {}, LineAssets(background_tags=["forest"]))]

    resolved = await service.match_assets(prepared, SceneAssets(), universe_id=1)

    assert resolved[0].background_asset_key == "bg/forest.png"
    assert resolved[0].sound_asset_key is None
