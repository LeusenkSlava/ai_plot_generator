from src.core.codex.models import Outfit, Tag
from src.outbound.codex.schemas import OutfitSchema, TagSchema


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
