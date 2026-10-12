"""Вспомогательные функции для работы со списком персонажей в промптах."""

from src.core.novels.models import Character


def find_protagonist(characters: list[Character]) -> Character | None:
    """Главный герой новеллы или None, если он не помечен."""
    return next((c for c in characters if c.is_protagonist), None)


def render_cast(characters: list[Character]) -> str:
    """Список персонажей для промпта с пометкой протагониста."""
    lines = []
    for c in characters:
        role = c.role
        if c.is_protagonist:
            role = f"{role} (протагонист)"
        lines.append(f"- {c.name} ({role}): {c.voice_notes}")
    return "\n".join(lines)
