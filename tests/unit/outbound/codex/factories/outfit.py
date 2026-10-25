from src.core.codex.models import Emotion, Outfit, OutfitWithEmotions, Tag
from src.outbound.codex.schemas import (
    EmotionSchema,
    OutfitCatalogSchema,
    OutfitSchema,
    TagSchema,
)


def outfit_payload(
    *,
    id: int = 1,
    sprite_id: int = 1,
    slug: str = "casual",
    name: str = "Casual",
    asset_key: str = "outfits/casual.png",
    tags: list[dict] | None = None,
) -> dict:
    return OutfitSchema(
        id=id,
        sprite_id=sprite_id,
        slug=slug,
        name=name,
        asset_key=asset_key,
        tags=[TagSchema(**t) for t in (tags or [])],
    ).model_dump(mode="json")


def outfit_domain(
    *,
    id: int = 1,
    sprite_id: int = 1,
    slug: str = "casual",
    name: str = "Casual",
    asset_key: str = "outfits/casual.png",
    tags: list[Tag] | None = None,
) -> Outfit:
    return Outfit(
        id=id,
        sprite_id=sprite_id,
        slug=slug,
        name=name,
        asset_key=asset_key,
        tags=tags or [],
    )


def outfit_catalog_payload(
    *,
    id: int = 1,
    sprite_id: int = 1,
    slug: str = "casual",
    name: str = "Casual",
    asset_key: str = "outfits/casual.png",
    tags: list[dict] | None = None,
    emotions: list[dict] | None = None,
) -> dict:
    """Элемент каталога нарядов: наряд + вложенные эмоции (payload)."""
    return OutfitCatalogSchema(
        id=id,
        sprite_id=sprite_id,
        slug=slug,
        name=name,
        asset_key=asset_key,
        tags=[TagSchema(**t) for t in (tags or [])],
        emotions=[EmotionSchema(**e) for e in (emotions or [])],
    ).model_dump(mode="json")


def outfit_with_emotions_domain(
    *,
    outfit: Outfit | None = None,
    emotions: list[Emotion] | None = None,
) -> OutfitWithEmotions:
    """Наряд с эмоциями в доменном виде."""
    return OutfitWithEmotions(
        outfit=outfit or outfit_domain(),
        emotions=list(emotions) if emotions is not None else [],
    )
