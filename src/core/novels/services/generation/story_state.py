"""Состояние изложения истории и чистые хелперы для промптов (без LLM и БД).

Вынесено из ``generators/story_context.py``, чтобы ``DialogueContextLoader``
(``generation/context.py``) и генераторы могли импортировать
``StoryState``/``render_story_context``/``extract_used_phrases``, не затягивая
пакет ``generators`` и не создавая циклический импорт.
"""

import json
import re
from dataclasses import asdict, dataclass, field

MAX_KEY_FACTS = 12
# Максимум повторяющихся фраз (n-грамм), которые код кладёт в «не повторять дословно».
MAX_USED_PHRASES = 5
# Минимальный возраст факта (в итерациях apply), после которого его можно удалять.
# Факт, добавленный в текущей или предыдущей итерации, удалять нельзя — иначе
# редактор стирает только что записанные факты.
MIN_FACT_AGE_TO_REMOVE = 2


def _normalize(text: str) -> str:
    """Нормализация текста для сравнения фактов: регистр, пунктуация, лишние пробелы."""
    return re.sub(r"[^\wа-яё0-9]+", " ", text.lower()).strip()


def _cast_name_tokens(names: list[str]) -> set[str]:
    """Все нормализованные слова имён персонажей — для отсева имён из стоп-фраз.

    Многословное имя («Ольга Дмитриевна») разбивается на слова, чтобы ловить
    упоминание по любому из них.
    """
    tokens: set[str] = set()
    for name in names:
        if not name:
            continue
        for token in _normalize(name).split():
            tokens.add(token)
    return tokens


def _word_tokens(text: str) -> list[str]:
    """Слова реплики после нормализации — для извлечения n-грамм."""
    return [t for t in _normalize(text).split() if t]


def extract_used_phrases(
    lines: list[str], names: list[str], max_phrases: int = MAX_USED_PHRASES
) -> list[str]:
    """Повторяющиеся словосочетания из прошлых реплик — для блока «не повторять дословно».

    Считаются триграммы и биграммы, встретившиеся минимум в двух репликах. Имена
    персонажей и всё, что содержит имя, отсеивается, чтобы не запрещать упоминание
    героев. Приоритет — более длинные и частые фразы; короткая фраза, поглощённая
    длинной, не дублируется.
    """
    name_tokens = _cast_name_tokens(names)
    line_counts: dict[str, int] = {}
    for line in lines:
        tokens = _word_tokens(line)
        grams: set[str] = set()
        for n in (3, 2):
            for i in range(len(tokens) - n + 1):
                gram = tuple(tokens[i : i + n])
                if any(token in name_tokens for token in gram):
                    continue
                grams.add(" ".join(gram))
        for phrase in grams:
            line_counts[phrase] = line_counts.get(phrase, 0) + 1

    repeated = [p for p, count in line_counts.items() if count >= 2]
    repeated.sort(key=lambda p: (-len(p.split()), -line_counts[p]))
    result: list[str] = []
    for phrase in repeated:
        if len(result) >= max_phrases:
            break
        if any(phrase in kept for kept in result):
            continue
        result.append(phrase)
    return result


@dataclass
class StoryState:
    """Изложение истории после сцены. Хранится в scenes.story_context как JSON."""

    key_facts: list[str] = field(default_factory=list)
    # возраст каждого факта в итерациях apply (выравнен с key_facts)
    fact_ages: list[int] = field(default_factory=list)
    # имя персонажа -> {"outfit": ..., "state": ...}
    characters: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, raw: str | None) -> "StoryState":
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
        except ValueError:
            # Изложение в старом формате — просто текст; держим его как один факт.
            return cls(key_facts=[raw])
        key_facts = list(data.get("key_facts") or [])
        raw_ages = data.get("fact_ages")
        if raw_ages is None:
            # Старые данные без возрастов: считаем все факты «взрослыми» (удаляемыми).
            fact_ages = [MIN_FACT_AGE_TO_REMOVE] * len(key_facts)
        else:
            fact_ages = [int(a) for a in raw_ages]
        return cls(
            key_facts=key_facts,
            fact_ages=fact_ages,
            characters=dict(data.get("characters") or {}),
        )

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    def apply(self, delta: dict) -> list[tuple[int, str]]:
        """Применяет изменения от LLM: удалённые/добавленные факты, изменившихся персонажей.

        Возвращает список (номер, текст) фактов, удаление которых было отклонено,
        потому что факт слишком свежий (возраст < MIN_FACT_AGE_TO_REMOVE).
        """
        removed = {i for i in delta.get("remove_facts") or [] if isinstance(i, int)}
        self._align_ages()
        protected: list[tuple[int, str]] = []
        kept_facts: list[str] = []
        kept_ages: list[int] = []
        for i, fact in enumerate(self.key_facts, start=1):
            age = self.fact_ages[i - 1]
            if i in removed and age < MIN_FACT_AGE_TO_REMOVE:
                # Свежий факт не удаляем — защищаем от стирания только что записанного.
                protected.append((i, fact))
                kept_facts.append(fact)
                kept_ages.append(age)
            elif i in removed:
                continue  # взрослый факт — удаляем
            else:
                kept_facts.append(fact)
                kept_ages.append(age)

        # Выжившие факты стареют на одну итерацию.
        kept_ages = [age + 1 for age in kept_ages]
        self.key_facts, self.fact_ages = self.__merge_facts(
            kept_facts, kept_ages, delta.get("add_facts") or []
        )

        for c in delta.get("characters") or []:
            if not c.get("name"):
                continue
            current = self.characters.setdefault(c["name"], {})
            for key in ("outfit", "state"):
                if value := (c.get(key) or "").strip():
                    current[key] = value
        return protected

    def _align_ages(self) -> None:
        """Выравнивает fact_ages под key_facts; отсутствующие возраста считаем «взрослыми».

        Нужно для старых данных и прямой конструкции StoryState(key_facts=...) в тестах,
        где fact_ages не задан.
        """
        if len(self.fact_ages) < len(self.key_facts):
            self.fact_ages = self.fact_ages + [MIN_FACT_AGE_TO_REMOVE] * (
                len(self.key_facts) - len(self.fact_ages)
            )
        elif len(self.fact_ages) > len(self.key_facts):
            self.fact_ages = self.fact_ages[: len(self.key_facts)]

    @staticmethod
    def __merge_facts(
        existing: list[str], existing_ages: list[int], added: list[str]
    ) -> tuple[list[str], list[int]]:
        """Склейка фактов без дублей: точный повтор/вложенность отбрасывается,
        а факт, поглощающий существующий, заменяет его. Самые старые уходят первыми.

        Новые (и поглотившие старые) факты получают возраст 0 — они свежие и
        защищены от удаления в следующих итерациях.
        """
        result = list(existing)
        ages = list(existing_ages)
        for fact in added:
            fact = fact.strip()
            if not fact:
                continue
            norm = _normalize(fact)
            duplicate = False
            absorbed_index: int | None = None
            for i, old in enumerate(result):
                old_norm = _normalize(old)
                if not old_norm:
                    continue
                if norm == old_norm or norm in old_norm:
                    duplicate = True
                    break
                if old_norm in norm:
                    absorbed_index = i
                    break
            if duplicate:
                continue
            if absorbed_index is not None:
                result[absorbed_index] = fact
                ages[absorbed_index] = 0
            else:
                result.append(fact)
                ages.append(0)
        if len(result) > MAX_KEY_FACTS:
            result = result[-MAX_KEY_FACTS:]
            ages = ages[-MAX_KEY_FACTS:]
        return result, ages

    def render(self, numbered: bool = False) -> str:
        """Текст изложения для промтов."""
        parts = []
        if self.key_facts:
            parts.append(
                "Important plot facts:\n"
                + "\n".join(
                    f"{i}. {f}" if numbered else f"- {f}"
                    for i, f in enumerate(self.key_facts, 1)
                )
            )
        if self.characters:
            parts.append(
                "Character states:\n"
                + "\n".join(
                    f"- {name}: outfit — {c.get('outfit') or 'not specified'}; "
                    f"state — {c.get('state') or 'not specified'}"
                    for name, c in self.characters.items()
                )
            )
        return "\n\n".join(parts)


def render_story_context(raw: str | None) -> str | None:
    """scenes.story_context -> текст для промтов сцены и диалога."""
    return StoryState.load(raw).render() or None
