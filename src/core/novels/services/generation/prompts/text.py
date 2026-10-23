"""Вспомогательные функции форматирования текста для промптов."""

RUSSIAN_OUTPUT_NOTE = (
    "Write all generated content in Russian; write proper names in Russian."
)


def single_line(text: str) -> str:
    """Схлопывает переносы строк и повторные пробелы в одну строку.

    Описания из Codex приходят многоабзацными (например, «живёт в домике с ...»
    отдельным абзацем). В промпте весь текст должен относиться к одному пункту,
    поэтому переносы заменяем на пробелы.
    """
    return " ".join(text.split())


def parse_day(value) -> int | None:
    """Парсит номер дня истории (целое, >= 1); None, если не задан или некорректен."""
    if value is None:
        return None
    try:
        day = int(value)
    except (TypeError, ValueError):
        return None
    return day if day >= 1 else None
