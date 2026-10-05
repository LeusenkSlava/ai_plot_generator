from src.core.codex.models import Sprite, Tag
from src.outbound.codex.schemas import SpriteSchema, TagSchema


def sprite_payload(
    *,
    id: int = 1,
    character_id: int = 1,
    slug: str = "alice-base",
    description: str = "Базовый спрайт",
    asset_key: str = "sprites/alice.png",
    tags: list[dict] | None = None,
) -> dict:
    return SpriteSchema(
        id=id,
        character_id=character_id,
        slug=slug,
        description=description,
        asset_key=asset_key,
        tags=[TagSchema(**t) for t in (tags or [])],
    ).model_dump(mode="json")


def sprite_domain(
    *,
    id: int = 1,
    character_id: int = 1,
    slug: str = "alice-base",
    description: str = "Базовый спрайт",
    asset_key: str = "sprites/alice.png",
    tags: list[Tag] | None = None,
) -> Sprite:
    return Sprite(
        id=id,
        character_id=character_id,
        slug=slug,
        description=description,
        asset_key=asset_key,
        tags=tags or [],
    )
