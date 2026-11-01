"""Форматирование реплик диалога для показа человеку.

Единственная точка, где сырой JSON-ответ диалога (``dialogue_lines``) превращается
в строки вида ``[описание] …`` / ``* Имя (мысль): …`` / ``Имя: …``. Переиспользуется
админкой (тест промпта) и скриптом ``regen_dialogue.py``, чтобы убрать дубли
``render_lines``.
"""

from __future__ import annotations


def format_dialogue_lines(data: dict) -> list[str]:
    """Превращает сырой JSON-ответ диалога в список отформатированных реплик."""
    out: list[str] = []
    for line in data.get("dialogue_lines") or []:
        kind = line.get("kind")
        text = (line.get("text") or "").strip()
        name = (line.get("character_name") or "").strip()
        if kind == "narration":
            out.append(f"[описание] {text}")
        elif kind == "thought":
            out.append(f"* {name} (мысль): {text}")
        else:
            out.append(f"{name}: {text}")
    return out
