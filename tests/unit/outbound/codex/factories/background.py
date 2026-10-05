from src.core.codex.models import Background, Tag
from src.outbound.codex.schemas import BackgroundSchema, TagSchema


def background_payload(
    *,
    id: int = 1,
    universe_id: int = 1,
    slug: str = "forest",
    description: str = "Лес",
    asset_key: str = "bg/forest.png",
    tags: list[dict] | None = None,
) -> dict:
    return BackgroundSchema(
        id=id,
        universe_id=universe_id,
        slug=slug,
        description=description,
        asset_key=asset_key,
        tags=[TagSchema(**t) for t in (tags or [])],
    ).model_dump(mode="json")


def background_domain(
    *,
    id: int = 1,
    universe_id: int = 1,
    slug: str = "forest",
    description: str = "Лес",
    asset_key: str = "bg/forest.png",
    tags: list[Tag] | None = None,
) -> Background:
    return Background(
        id=id,
        universe_id=universe_id,
        slug=slug,
        description=description,
        asset_key=asset_key,
        tags=tags or [],
    )
