"""Форматтер контекста вселенной Codex для промптов генераторов.

Чистые функции без IO: генераторы сами загружают данные вселенной из Codex
(через CodexService), а сюда передают уже готовые модели. Благодаря этому одни
и те же сущности (вселенная, персонажи, локации) описываются в промптах одинаково.
"""

from src.core.codex.models import Background, BackgroundTags, CodexCharacter, Tag, TagType, Universe
from src.core.novels.services.generation.prompts.text import single_line


def render_universe(universe: Universe) -> str:
    return f"Вселенная: {universe.title}\n{universe.description}"


def render_characters(characters: list[CodexCharacter]) -> str:
    return (
        "Персонажи (других нет):\n"
        + "\n".join(f"- {c.name}: {single_line(c.description)}" for c in characters)
    )


def render_character_catalog(characters: list[CodexCharacter]) -> str:
    """Подробный каталог персонажей (slug, манера речи, теги) для генератора
    персонажей, где LLM ссылается на персонажа по codex_slug."""
    return "\n".join(
        f"- slug: {c.slug}; имя: {c.name}; описание: {single_line(c.description)}"
        + (f"; манера речи: {c.speech_style}" if c.speech_style else "")
        + (f"; теги: {', '.join(t.name for t in c.tags)}" if c.tags else "")
        for c in characters
    )


def render_locations(backgrounds: list[Background]) -> str:
    return (
        "Локации (других нет):\n"
        + "\n".join(render_background(b) for b in backgrounds)
    )


def render_background(background: Background) -> str:
    """Одна локация для промпта: название + теги."""
    tags = ", ".join(t.name for t in background.tags)
    line = f"- {background.description}"
    if tags:
        line += f" (теги: {tags})"
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
    times = ", ".join(f"{t.slug}={t.name}" for t in time_of_day_tags(background_tags)) or "-"
    return (
        f"Локации (location_slug, ТОЛЬКО из списка): {locations}\n"
        f"Время суток (time_of_day, ТОЛЬКО из списка): {times}"
    )


def render_place_time(
    location_slug: str | None,
    time_of_day: str | None,
    day: int | None,
) -> str:
    """Короткая строка «локация / время суток / день» для промпта; «не задано» при пустом."""
    parts: list[str] = []
    if location_slug:
        parts.append(f"локация {location_slug}")
    if time_of_day:
        parts.append(f"время суток {time_of_day}")
    if day is not None:
        parts.append(f"день {day}")
    return ", ".join(parts) if parts else "не задано"
