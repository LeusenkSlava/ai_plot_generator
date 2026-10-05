from src.core.codex.models import Background, CodexCharacter, Universe


def universe_domain(
    *,
    id: int = 1,
    slug: str = "mir-tmy",
    title: str = "Мир Тьмы",
    description: str = "Мрачное средневековье",
) -> Universe:
    return Universe(id=id, slug=slug, title=title, description=description)


def character_domain(
    *,
    id: int = 1,
    universe_id: int = 1,
    slug: str = "alice",
    name: str = "Алиса",
    description: str = "Ведьма",
) -> CodexCharacter:
    return CodexCharacter(
        id=id,
        universe_id=universe_id,
        slug=slug,
        name=name,
        description=description,
    )


def background_domain(
    *,
    id: int = 1,
    universe_id: int = 1,
    slug: str = "forest",
    description: str = "Лес",
    asset_key: str = "bg/forest.png",
) -> Background:
    return Background(
        id=id,
        universe_id=universe_id,
        slug=slug,
        description=description,
        asset_key=asset_key,
    )
