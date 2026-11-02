"""Юнит-тесты SceneAssetService: резолв ассетов сцены через Codex."""

from src.core.codex.models import TagKind, VisualMatch
from src.core.novels.services.generation.assets import (
    LineAssets,
    SceneAssets,
    SceneAssetService,
)
from tests.factories import background_domain, novel_character_domain
from tests.fakes.outbound.codex.client import FakeCodexService
from tests.unit.outbound.codex.factories import (
    outfit_emotion_domain,
    outfit_with_emotions_domain,
)


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


async def test_match_assets_sets_outfit_tag_from_line():
    """Подобранный визуал сохраняет style-тег, которым наряд был адресован."""
    codex = FakeCodexService()
    character = novel_character_domain(
        id=1, novel_id=1, name="Алиса", codex_character_id=10
    )
    codex.set_match_visual(
        10,
        "camp_uniform",
        ["smile"],
        VisualMatch(
            sprite_asset_key="sprites/alice.png",
            outfit_asset_key="outfits/uniform.png",
            emotion_asset_key="emotions/smile.png",
        ),
    )
    prepared = [
        (character, {}, LineAssets(outfit_tag="camp_uniform", emotion_tags=["smile"]))
    ]

    resolved = await SceneAssetService(codex).match_assets(
        prepared, SceneAssets(), universe_id=None
    )

    assert resolved[0].outfit_tag == "camp_uniform"
    assert resolved[0].outfit_asset_key == "outfits/uniform.png"


# ---------------------------------------------------------------------------
# Каталог нарядов: Codex уже сгруппировал по style-тегу, клиент рендерит как есть
# ---------------------------------------------------------------------------

def _catalog_sections(catalog: str) -> dict[str, str]:
    """Разбивает каталог на секции по строкам «- outfit_tag (Имя):»."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in catalog.splitlines():
        if line.startswith("- "):
            current = line[2:].split(" (", 1)[0]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {tag: "\n".join(lines) for tag, lines in sections.items()}


def test_catalog_renders_each_outfit_tag_once():
    """Каждая группа Codex рендерится ровно одной строкой с эмоциями."""
    character = novel_character_domain(
        id=1, novel_id=1, name="Алиса", codex_character_id=1
    )
    assets = SceneAssets(
        outfits={
            1: [
                outfit_with_emotions_domain(
                    outfit_tag="camp_uniform",
                    name="Форма вожатого",
                    emotions=[
                        outfit_emotion_domain(
                            slug="smile", name="Улыбка", kind=TagKind.BASE
                        ),
                    ],
                ),
                outfit_with_emotions_domain(
                    outfit_tag="swimsuit",
                    name="Купальник",
                    emotions=[
                        outfit_emotion_domain(
                            slug="grin", name="Ухмылка", kind=TagKind.BASE
                        ),
                        outfit_emotion_domain(
                            slug="tears", name="Со слезами", kind=TagKind.MODIFIER
                        ),
                    ],
                ),
            ]
        }
    )

    catalog = SceneAssetService.assets_catalog([character], assets)

    assert catalog.count("- camp_uniform (") == 1
    assert catalog.count("- swimsuit (") == 1
    sections = _catalog_sections(catalog)
    assert set(sections) == {"camp_uniform", "swimsuit"}
    assert "smile=Улыбка" in sections["camp_uniform"]
    assert "smile=Улыбка" not in sections["swimsuit"]
    assert "grin=Ухмылка" in sections["swimsuit"]
    assert "tears=Со слезами" in sections["swimsuit"]


def test_emotions_for_outfit_splits_base_and_modifiers():
    """emotions_for_outfit отдаёт base и modifier-слаги выбранного style-тега."""
    character = novel_character_domain(
        id=1, novel_id=1, name="Алиса", codex_character_id=1
    )
    assets = SceneAssets(
        outfits={
            1: [
                outfit_with_emotions_domain(
                    outfit_tag="swimsuit",
                    name="Купальник",
                    emotions=[
                        outfit_emotion_domain(
                            slug="grin", name="Ухмылка", kind=TagKind.BASE
                        ),
                        outfit_emotion_domain(
                            slug="tears", name="Со слезами", kind=TagKind.MODIFIER
                        ),
                    ],
                )
            ]
        }
    )

    base, modifiers = SceneAssetService.emotions_for_outfit(
        assets, character.codex_character_id, "swimsuit"
    )

    assert base == ["grin"]
    assert modifiers == ["tears"]


def test_current_outfits_uses_stored_style_tag():
    """Последний наряд берётся из сохранённого style-тега, а не из каталога."""
    character = novel_character_domain(
        id=1, novel_id=1, name="Алиса", codex_character_id=1
    )
    assets = SceneAssets(
        outfits={
            1: [
                outfit_with_emotions_domain(
                    outfit_tag="swimsuit", name="Купальник"
                ),
            ]
        }
    )

    rendered = SceneAssetService.current_outfits(
        [character], assets, {character.id: "swimsuit"}
    )

    assert rendered == "- Алиса: outfit_tag swimsuit (Купальник)"x
