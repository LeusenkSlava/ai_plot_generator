"""Юнит-тесты SceneAssetService: резолв ассетов сцены через Codex."""

import logging

from src.core.codex.models import BackgroundTags, Tag, TagKind, TagType, VisualMatch
from src.core.novels.services.generation.assets import (
    BackgroundChange,
    BackgroundSegment,
    LineAssets,
    SceneAssets,
    SceneAssetService,
)
from tests.factories import background_domain, novel_character_domain, scene_domain
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


def test_anchor_background_tags_uses_scene_location_and_forced_time():
    """База = локация сцены; время суток принудительно из сцены, а не из LLM."""
    scene = scene_domain(location_slug="beach", time_of_day="night")
    assets = SceneAssets(
        background_tags=BackgroundTags(
            base=[Tag(id=1, type=TagType.LOCATION, slug="beach", name="Пляж")],
            modifiers=[
                Tag(id=2, type=TagType.TIME_OF_DAY, slug="day", name="День"),
                Tag(id=3, type=TagType.TIME_OF_DAY, slug="night", name="Ночь"),
                Tag(id=4, type=TagType.LOCATION, slug="with_people", name="С людьми"),
            ],
        )
    )

    tags = SceneAssetService.anchor_background_tags(
        scene, ["day", "with_people"], assets
    )

    assert tags == ["beach", "with_people", "night"]


def test_anchor_background_tags_none_without_location():
    """Без локации сцены якорь фона не строится (обратная совместимость)."""
    scene = scene_domain(location_slug=None)
    assets = SceneAssets(
        background_tags=BackgroundTags(
            base=[Tag(id=1, type=TagType.LOCATION, slug="beach", name="Пляж")],
            modifiers=[],
        )
    )

    assert SceneAssetService.anchor_background_tags(scene, [], assets) is None


def test_background_tags_warns_when_model_supplies_time_of_day(caplog):
    """Попытка модели задать время суток логируется, а не теряется молча."""
    scene = scene_domain(location_slug="beach", time_of_day="night")
    assets = SceneAssets(
        background_tags=BackgroundTags(
            base=[Tag(id=1, type=TagType.LOCATION, slug="beach", name="Пляж")],
            modifiers=[
                Tag(id=2, type=TagType.TIME_OF_DAY, slug="day", name="День"),
                Tag(id=3, type=TagType.TIME_OF_DAY, slug="night", name="Ночь"),
            ],
        )
    )

    with caplog.at_level(
        logging.WARNING,
        logger="src.core.novels.services.generation.assets",
    ):
        tags = SceneAssetService.anchor_background_tags(scene, ["day"], assets)

    assert tags == ["beach", "night"]
    assert "overridden by scene.time_of_day" in caplog.text
    assert "['day']" in caplog.text


def _segment_assets() -> SceneAssets:
    return SceneAssets(
        background_tags=BackgroundTags(
            base=[
                Tag(id=1, type=TagType.LOCATION, slug="beach", name="Пляж"),
                Tag(id=6, type=TagType.LOCATION, slug="gate", name="Ворота"),
            ],
            modifiers=[
                Tag(id=2, type=TagType.TIME_OF_DAY, slug="day", name="День"),
                Tag(id=3, type=TagType.TIME_OF_DAY, slug="night", name="Ночь"),
                Tag(id=4, type=TagType.LOCATION, slug="inside", name="Внутри"),
                Tag(id=5, type=TagType.LOCATION, slug="outside", name="Снаружи"),
            ],
        )
    )


def test_anchor_background_tags_per_line_applies_changes_at_line():
    """Смена фона действует с указанной реплики; время суток принудительно из сцены."""
    scene = scene_domain(location_slug="beach", time_of_day="night")

    segments = SceneAssetService.anchor_background_tags_per_line(
        scene, ["inside"], [BackgroundChange(3, None, ["outside"])], 5, _segment_assets()
    )

    assert [s.tags for s in segments] == [
        ["beach", "inside", "night"],
        ["beach", "inside", "night"],
        ["beach", "outside", "night"],
        ["beach", "outside", "night"],
        ["beach", "outside", "night"],
    ]
    assert [s.location_slug for s in segments] == ["beach"] * 5


def test_anchor_background_tags_per_line_changes_location():
    """Смена может явно поменять базовую локацию сегмента."""
    scene = scene_domain(location_slug="beach", time_of_day="night")

    segments = SceneAssetService.anchor_background_tags_per_line(
        scene, ["inside"], [BackgroundChange(3, "gate", ["outside"])], 4, _segment_assets()
    )

    assert [s.tags for s in segments] == [
        ["beach", "inside", "night"],
        ["beach", "inside", "night"],
        ["gate", "outside", "night"],
        ["gate", "outside", "night"],
    ]
    assert [s.location_slug for s in segments] == ["beach", "beach", "gate", "gate"]


def test_anchor_background_tags_per_line_ignores_unknown_location():
    """Неизвестная локация смены игнорируется — остаётся текущая база."""
    scene = scene_domain(location_slug="beach", time_of_day="night")

    segments = SceneAssetService.anchor_background_tags_per_line(
        scene, [], [BackgroundChange(2, "forest", [])], 3, _segment_assets()
    )

    assert [s.tags for s in segments] == [
        ["beach", "night"],
        ["beach", "night"],
        ["beach", "night"],
    ]


def test_anchor_background_tags_per_line_none_without_anchor():
    """Без вселенной/локации все реплики получают tags=None (фон не резолвится)."""
    scene = scene_domain(location_slug=None)

    segments = SceneAssetService.anchor_background_tags_per_line(
        scene, [], [], 3, _segment_assets()
    )

    assert segments == [BackgroundSegment(None, None)] * 3


def test_normalize_background_changes_filters_invalid():
    """Невалидные/дублирующиеся смены отбрасываются, результат отсортирован."""
    raw = [
        {"at_line": 3, "location_slug": "gate", "background_modifier_tags": ["outside"]},
        {"at_line": 1, "background_modifier_tags": ["inside"]},
        {"at_line": 99, "background_modifier_tags": ["x"]},  # вне диапазона
        {"at_line": 3, "background_modifier_tags": ["y"]},  # дубль at_line
        {"at_line": 4, "background_modifier_tags": []},  # без локации и модификаторов
        {"at_line": "5", "background_modifier_tags": ["z"]},  # строковый индекс
        {"at_line": 6, "background_modifier_tags": "bad"},  # не-список
        "not-a-dict",
    ]

    changes = SceneAssetService.normalize_background_changes(raw, 5)

    assert changes == [
        BackgroundChange(1, None, ["inside"]),
        BackgroundChange(3, "gate", ["outside"]),
        BackgroundChange(5, None, ["z"]),
    ]


async def test_match_assets_reuses_scene_background_for_all_lines():
    """Одинаковый набор тегов резолвится один раз и раздаётся всем репликам."""
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
    character = novel_character_domain(
        id=1, novel_id=1, name="Алиса", role="Ведьма", is_protagonist=True,
    )
    prepared = [(character, {}, LineAssets()), (character, {}, LineAssets())]

    resolved = await service.match_assets(
        prepared, SceneAssets(), universe_id=1,
        line_background_tags=[["forest"], ["forest"]],
    )

    assert [r.background_asset_key for r in resolved] == ["bg/forest.png", "bg/forest.png"]
    bg_calls = [c for c in codex.calls if c[0] == "match_background"]
    assert len(bg_calls) == 1


async def test_match_assets_resolves_distinct_backgrounds_per_segment():
    """Разные наборы тегов дают разные фоны; одинаковые — резолвятся один раз."""
    codex = FakeCodexService()
    codex.add_backgrounds(
        1,
        [
            background_domain(
                id=1, universe_id=1, slug="forest", description="Лес",
                asset_key="bg/forest.png",
            ),
            background_domain(
                id=2, universe_id=1, slug="beach", description="Пляж",
                asset_key="bg/beach.png",
            ),
        ],
    )

    service = SceneAssetService(codex)
    character = novel_character_domain(
        id=1, novel_id=1, name="Алиса", role="Ведьма", is_protagonist=True,
    )
    prepared = [
        (character, {}, LineAssets()),
        (character, {}, LineAssets()),
        (character, {}, LineAssets()),
    ]

    resolved = await service.match_assets(
        prepared, SceneAssets(), universe_id=1,
        line_background_tags=[["forest"], ["beach"], ["beach"]],
    )

    assert [r.background_asset_key for r in resolved] == [
        "bg/forest.png",
        "bg/beach.png",
        "bg/beach.png",
    ]
    bg_calls = [c for c in codex.calls if c[0] == "match_background"]
    assert len(bg_calls) == 2


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

    assert rendered == "- Алиса: outfit_tag swimsuit (Купальник)"
