from src.core.codex.models import (
    Background,
    BackgroundTags,
    CodexCharacter,
    Tag,
    TagType,
    Universe,
)
from src.core.novels.services.generation.prompts.text import single_line


def render_universe(universe: Universe) -> str:
    return f"Universe: {universe.title}\n{universe.description}"


def render_characters(characters: list[CodexCharacter]) -> str:
    return "Characters (there are no others):\n" + "\n".join(
        f"- {c.name}"
        + (f" ({c.gender})" if c.gender else "")
        + f": {single_line(c.description)}"
        for c in characters
    )


def render_character_catalog(characters: list[CodexCharacter]) -> str:
    """Подробный каталог персонажей (slug, манера речи, пол, теги) для генератора
    персонажей, где LLM ссылается на персонажа по codex_slug."""
    return "\n".join(
        f"- slug: {c.slug}; name: {c.name}; description: {single_line(c.description)}"
        + (f"; gender: {c.gender}" if c.gender else "")
        + (f"; speech style: {c.speech_style}" if c.speech_style else "")
        + (f"; tags: {', '.join(t.name for t in c.tags)}" if c.tags else "")
        for c in characters
    )


def render_locations(backgrounds: list[Background]) -> str:
    return "Locations (there are no others):\n" + "\n".join(
        render_background(b) for b in backgrounds
    )


def render_background(background: Background) -> str:
    """Одна локация для промпта: название + теги."""
    tags = ", ".join(t.name for t in background.tags)
    line = f"- {background.description}"
    if tags:
        line += f" (tags: {tags})"
    return line


def render_all(
    universe: Universe,
    characters: list[CodexCharacter],
    backgrounds: list[Background],
) -> str:
    """Полный контекст вселенной: вселенная, персонажи и локации."""
    parts = [render_universe(universe)]
    if characters:
        parts.append(render_characters(characters))
    if backgrounds:
        parts.append(render_locations(backgrounds))
    return "\n\n".join(parts)


def time_of_day_tags(background_tags: BackgroundTags) -> list[Tag]:
    """Теги времени суток из уточнений фонов вселенной (day/morning/night)."""
    return [t for t in background_tags.modifiers if t.type == TagType.TIME_OF_DAY]


def render_place_time_catalog(background_tags: BackgroundTags) -> str:
    """Каталог локаций и времени суток для выбора место/времени шага роадмапа."""
    locations = ", ".join(f"{t.slug}={t.name}" for t in background_tags.base) or "-"
    times = (
        ", ".join(f"{t.slug}={t.name}" for t in time_of_day_tags(background_tags))
        or "-"
    )
    return (
        f"Locations (location_slug, ONLY from the list): {locations}\n"
        f"Time of day (time_of_day, ONLY from the list): {times}"
    )


def render_place_time(
    location_slug: str | None,
    time_of_day: str | None,
    day: int | None,
) -> str:
    """Короткая строка «локация / время суток / день» для промпта; «не задано» при пустом."""
    parts: list[str] = []
    if location_slug:
        parts.append(f"location {location_slug}")
    if time_of_day:
        parts.append(f"time of day {time_of_day}")
    if day is not None:
        parts.append(f"day {day}")
    return ", ".join(parts) if parts else "not set"
