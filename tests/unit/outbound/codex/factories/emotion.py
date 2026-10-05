from src.core.codex.models import Emotion, Tag
from src.outbound.codex.schemas import EmotionSchema, TagSchema


def emotion_payload(
    *,
    id: int = 1,
    sprite_id: int = 1,
    slug: str = "happy",
    name: str = "Happy",
    asset_key: str = "emotions/happy.png",
    tags: list[dict] | None = None,
) -> dict:
    return EmotionSchema(
        id=id,
        sprite_id=sprite_id,
        slug=slug,
        name=name,
        asset_key=asset_key,
        tags=[TagSchema(**t) for t in (tags or [])],
    ).model_dump(mode="json")


def emotion_domain(
    *,
    id: int = 1,
    sprite_id: int = 1,
    slug: str = "happy",
    name: str = "Happy",
    asset_key: str = "emotions/happy.png",
    tags: list[Tag] | None = None,
) -> Emotion:
    return Emotion(
        id=id,
        sprite_id=sprite_id,
        slug=slug,
        name=name,
        asset_key=asset_key,
        tags=tags or [],
    )
