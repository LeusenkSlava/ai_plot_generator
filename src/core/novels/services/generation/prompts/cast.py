"""Вспомогательные функции для работы со списком персонажей в промптах."""

from src.core.novels.models import Character


def find_protagonist(characters: list[Character]) -> Character | None:
    """Главный герой новеллы или None, если он не помечен."""
    return next((c for c in characters if c.is_protagonist), None)


def render_cast(characters: list[Character]) -> str:
    """Список персонажей для промпта с пометкой протагониста и пола."""
    lines = []
    for c in characters:
        role = c.role
        if c.is_protagonist:
            role = f"{role} (protagonist)"
        if c.gender:
            role = f"{role}, {c.gender}"
        lines.append(f"- {c.name} ({role}): {c.voice_notes}")
    return "\n".join(lines)


def render_characters_block(characters: list[Character]) -> str:
    """Блок каста для промптов plot_design и roadmap.

    Пустой каст — пустая строка (в шаблоне блок не появится). Если протагонист
    помечен, к списку добавляется абзац о том, что сюжет строится вокруг него.
    """
    if not characters:
        return ""
    block = f"\nCharacters:\n{render_cast(characters)}"
    protagonist = find_protagonist(characters)
    if protagonist:
        block += (
            f"\n\nProtagonist: {protagonist.name} — the protagonist, through whose eyes the story is told. "
            f"Their arc: {protagonist.arc}. "
            "Build the plot around the protagonist: their goals, decisions, internal conflicts, and relationships."
        )
    return block
