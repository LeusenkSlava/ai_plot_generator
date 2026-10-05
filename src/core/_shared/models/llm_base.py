import json
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class LLMGeneratedModel:
    """Базовая модель для сущностей, которые будет схемой для LLM.

    Наследники должны объявить _LLM_FIELDS: {имя_поля: подсказка}.
    Поля из _LLM_FIELDS должны быть объявлены как обычные поля dataclass'а.
    """

    _LLM_FIELDS: ClassVar[dict[str, str]] = {}

    @classmethod
    def llm_schema(cls) -> dict[str, str]:
        """Поля, которые должна вернуть LLM: {имя: подсказка}."""
        if not cls._LLM_FIELDS:
            raise NotImplementedError(f"{cls.__name__} must define _LLM_FIELDS")
        return dict(cls._LLM_FIELDS)

    @classmethod
    def llm_json_instruction(cls) -> str:
        """Готовая инструкция для system-промпта."""
        schema = cls.llm_schema()
        lines = "\n".join(f"- {name}: {hint}" for name, hint in schema.items())
        json_shape = json.dumps(
            {name: "string" for name in schema},
            ensure_ascii=False,
            indent=2,
        )
        return (
            "Создай поля:\n" + lines + "\n"
            "Отвечай СТРОГО в формате JSON по схеме:\n" + json_shape
        )

    @classmethod
    def llm_values(cls, data: dict) -> dict:
        """Достаёт из ответа LLM только поля, объявленные в _LLM_FIELDS."""
        missing = [name for name in cls._LLM_FIELDS if name not in data]
        if missing:
            raise ValueError(f"{cls.__name__}: LLM response missing fields: {missing}")
        return {name: data[name] for name in cls._LLM_FIELDS}
