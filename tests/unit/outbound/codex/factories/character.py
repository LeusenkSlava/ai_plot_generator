from src.core.codex.models import CodexCharacter, Tag
from src.outbound.codex.schemas import CharacterSchema, TagSchema


def character_payload(
    *,
    id: int = 1,
    universe_id: int = 1,
    slug: str = "alice",
    name: str = "Алиса",
    description: str = "Ведьма",
    speech_style: dict | None = None,
    tags: list[dict] | None = None,
) -> dict:
    return CharacterSchema(
        id=id,
        universe_id=universe_id,
        slug=slug,
        name=name,
        description=description,
        speech_style=speech_style,
        tags=[TagSchema(**t) for t in (tags or [])],
    ).model_dump(mode="json")


def character_domain(
    *,
    id: int = 1,
    universe_id: int = 1,
    slug: str = "alice",
    name: str = "Алиса",
    description: str = "Ведьма",
    speech_style: dict | None = None,
    tags: list[Tag] | None = None,
) -> CodexCharacter:
    return CodexCharacter(
        id=id,
        universe_id=universe_id,
        slug=slug,
        name=name,
        description=description,
        speech_style=speech_style,
        tags=tags or [],
    )
