from src.core.codex.models import Universe
from src.outbound.codex.schemas import UniverseSchema


def universe_payload(
    *,
    id: int = 1,
    slug: str = "mir-tmy",
    title: str = "Мир Тьмы",
    description: str = "Мрачное средневековье",
) -> dict:
    return UniverseSchema(
        id=id, slug=slug, title=title, description=description
    ).model_dump(mode="json")


def universe_domain(
    *,
    id: int = 1,
    slug: str = "mir-tmy",
    title: str = "Мир Тьмы",
    description: str = "Мрачное средневековье",
) -> Universe:
    return Universe(id=id, slug=slug, title=title, description=description)
