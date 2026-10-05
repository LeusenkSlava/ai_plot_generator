from src.core.codex.models import Tag, TagType
from src.outbound.codex.schemas import TagSchema


def tag_payload(
    *,
    id: int = 1,
    type: TagType = TagType.ARCHETYPE,
    slug: str = "warrior",
    name: str = "Warrior",
) -> dict:
    return TagSchema(id=id, type=type, slug=slug, name=name).model_dump(mode="json")


def tag_domain(
    *,
    id: int = 1,
    type: TagType = TagType.ARCHETYPE,
    slug: str = "warrior",
    name: str = "Warrior",
) -> Tag:
    return Tag(id=id, type=type, slug=slug, name=name)


# --- типизированные хелперы, чтобы не помнить, какой TagType к чему ---


def location_tag_payload(
    *, id: int = 1, slug: str = "forest", name: str = "Forest"
) -> dict:
    return tag_payload(id=id, type=TagType.LOCATION, slug=slug, name=name)


def emotion_tag_payload(
    *, id: int = 1, slug: str = "happy", name: str = "Happy"
) -> dict:
    return tag_payload(id=id, type=TagType.EMOTION, slug=slug, name=name)


def archetype_tag_payload(
    *, id: int = 1, slug: str = "warrior", name: str = "Warrior"
) -> dict:
    return tag_payload(id=id, type=TagType.ARCHETYPE, slug=slug, name=name)


def outfit_style_tag_payload(
    *, id: int = 1, slug: str = "casual", name: str = "Casual"
) -> dict:
    return tag_payload(id=id, type=TagType.OUTFIT_STYLE, slug=slug, name=name)


def time_of_day_tag_payload(
    *, id: int = 1, slug: str = "night", name: str = "Night"
) -> dict:
    return tag_payload(id=id, type=TagType.TIME_OF_DAY, slug=slug, name=name)
