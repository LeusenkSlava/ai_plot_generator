import json
import logging
import re
from dataclasses import asdict, dataclass, field

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Character, DialogueLine, Novel, Scene
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.generators.base import BaseGenerator

logger = logging.getLogger(__name__)

MAX_KEY_FACTS = 12
# Единый источник лимита стоп-фраз: подставляется и в код, и в промпт,
# чтобы рассинхрон («до 5» в промпте при лимите 10) не повторялся.
MAX_USED_PHRASES = 5
# Минимальный возраст факта (в итерациях apply), после которого его можно удалять.
# Факт, добавленный в текущей или предыдущей итерации, удалять нельзя — иначе
# редактор стирает только что записанные факты.
MIN_FACT_AGE_TO_REMOVE = 2
# Длинные реплики в промпте изложения обрезаем: динамическая часть всё равно идёт
# по цене кэш-промаха, а полный текст реплик редактору изложения не нужен.
CONTEXT_LINE_MAX_CHARS = 300


def _normalize(text: str) -> str:
    """Нормализация текста для сравнения фактов: регистр, пунктуация, лишние пробелы."""
    return re.sub(r"[^\wа-яё0-9]+", " ", text.lower()).strip()


def _short_line(text: str) -> str:
    """Обрезает длинную реплику для промпта изложения, сохраняя одну строку."""
    text = " ".join(text.split())
    if len(text) <= CONTEXT_LINE_MAX_CHARS:
        return text
    return text[: CONTEXT_LINE_MAX_CHARS - 1].rstrip() + "…"


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


def _valid_used_phrase(phrase: str, name_tokens: set[str]) -> bool:
    """Стоп-фраза валидна, если в ней ≥2 слова и нет имени персонажа из каста.

    Однословные междометия/ремарки («наверное», «пионер») и имена («Ольга
    Дмитриевна», «Ульяна не глупая») отсеиваются. Проверка языко-независима:
    счёт по пробелам и точное совпадение токенов имён.
    """
    tokens = _normalize(phrase).split()
    if len(tokens) < 2:
        return False
    if any(token in name_tokens for token in tokens):
        return False
    return True


def _filter_used_phrases(phrases: list[str], name_tokens: set[str]) -> list[str]:
    """Оставляет только валидные стоп-фразы; невалидные отбрасывает."""
    kept: list[str] = []
    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        if _valid_used_phrase(phrase, name_tokens):
            kept.append(phrase)
    return kept


@dataclass
class StoryState:
    """Изложение истории после сцены. Хранится в scenes.story_context как JSON."""

    summary: str = ""
    key_facts: list[str] = field(default_factory=list)
    # возраст каждого факта в итерациях apply (выравнен с key_facts)
    fact_ages: list[int] = field(default_factory=list)
    # имя персонажа -> {"outfit": ..., "state": ...}
    characters: dict[str, dict[str, str]] = field(default_factory=dict)
    # фразы-мотивы, которые уже звучали и не должны повторяться дословно дальше
    used_phrases: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, raw: str | None) -> "StoryState":
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
        except ValueError:
            # Изложение в старом формате — просто текст
            return cls(summary=raw)
        key_facts = list(data.get("key_facts") or [])
        raw_ages = data.get("fact_ages")
        if raw_ages is None:
            # Старые данные без возрастов: считаем все факты «взрослыми» (удаляемыми).
            fact_ages = [MIN_FACT_AGE_TO_REMOVE] * len(key_facts)
        else:
            fact_ages = [int(a) for a in raw_ages]
        return cls(
            summary=data.get("summary") or "",
            key_facts=key_facts,
            fact_ages=fact_ages,
            characters=dict(data.get("characters") or {}),
            used_phrases=list(data.get("used_phrases") or []),
        )

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    def apply(self, delta: dict) -> list[tuple[int, str]]:
        """Применяет изменения от LLM: новое summary, удалённые/добавленные факты, изменившихся персонажей.

        Возвращает список (номер, текст) фактов, удаление которых было отклонено,
        потому что факт слишком свежий (возраст < MIN_FACT_AGE_TO_REMOVE).
        """
        if summary := (delta.get("summary") or "").strip():
            self.summary = summary

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

        for phrase in delta.get("used_phrases") or []:
            phrase = phrase.strip()
            if not phrase:
                continue
            if any(_normalize(phrase) == _normalize(p) for p in self.used_phrases):
                continue
            self.used_phrases.append(phrase)
        self.used_phrases = self.used_phrases[-MAX_USED_PHRASES:]
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
        if self.summary:
            parts.append(f"Краткое содержание:\n{self.summary}")
        if self.key_facts:
            parts.append(
                "Важные сюжетные факты:\n"
                + "\n".join(
                    f"{i}. {f}" if numbered else f"- {f}"
                    for i, f in enumerate(self.key_facts, 1)
                )
            )
        if self.characters:
            parts.append(
                "Состояние персонажей:\n"
                + "\n".join(
                    f"- {name}: одежда — {c.get('outfit') or 'не указана'}; "
                    f"состояние — {c.get('state') or 'не указано'}"
                    for name, c in self.characters.items()
                )
            )
        if self.used_phrases:
            parts.append(
                "Уже звучавшие фразы (не повторяй их дословно в следующих сценах):\n"
                + "\n".join(f"- {p}" for p in self.used_phrases)
            )
        return "\n\n".join(parts)

    def render_summary(self) -> str | None:
        """Только краткое содержание — для промптов, которым не нужны факты/фразы."""
        return self.summary or None


def render_story_context(raw: str | None) -> str | None:
    """scenes.story_context -> текст для промтов сцены и диалога."""
    return StoryState.load(raw).render() or None


def render_story_summary(raw: str | None) -> str | None:
    """scenes.story_context -> только summary (для валидатора шага)."""
    return StoryState.load(raw).render_summary()


class StoryContextGenerator(BaseGenerator):
    """Изложение истории после сцены.

    LLM возвращает только изменения относительно предыдущего изложения (новое summary,
    добавленные/удалённые факты, изменившиеся персонажи), склеиваем их в коде.
    Результат сохраняется в сцену JSON'ом (StoryState), генерация следующей сцены берёт его.
    """

    def __init__(
        self,
        novel_service: NovelService,
        roadmap_service: RoadmapService,
        scene_service: SceneService,
        character_service: CharacterService,
        dialogue_line_service: DialogueLineService,
        generator: GeneratorProtocol,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service
        self._scene_service = scene_service
        self._character_service = character_service
        self._dialogue_line_service = dialogue_line_service

    async def generate(self, scene_id: int, previous_context: str | None = None) -> str:
        scene = await self._scene_service.get(scene_id)
        if not scene:
            raise GenerationError(f"Scene with id {scene_id} not found")

        roadmap = await self._roadmap_service.get(scene.roadmap_id)
        if not roadmap:
            raise GenerationError(f"Roadmap with id {scene.roadmap_id} not found")

        novel = await self._novel_service.get(roadmap.novel_id)
        if not novel:
            raise GenerationError(f"Novel with id {roadmap.novel_id} not found")

        characters = await self._character_service.list_by_novel(novel.id) or []
        lines = await self._dialogue_line_service.list_by_scene(scene.id)
        name_tokens = _cast_name_tokens([c.name for c in characters])

        state = StoryState.load(previous_context)
        prompt = self.__create_prompt(novel, scene, characters, lines, state)

        # Один вызов LLM: изложение + фильтр стоп-фраз + склейка фактов в коде.
        # Смысловая дедупликация фактов и LLM-проверка противоречий убраны как
        # нерентабельные: проверка противоречий ловила ~1 случай на прогон при 52
        # микровызовах, а дубли гасит __merge_facts (точное/вложенное совпадение).
        delta = await self._generate(prompt, think=False)
        delta = dict(delta)
        # Валидация стоп-фраз: ≥2 слов и без имён персонажей (Задача 9).
        delta["used_phrases"] = _filter_used_phrases(
            delta.get("used_phrases") or [], name_tokens
        )

        protected = state.apply(delta)

        for index, fact in protected:
            logger.warning(
                "story_context: отказ удалять свежий факт #%s (%r): возраст < %s итераций",
                index,
                fact,
                MIN_FACT_AGE_TO_REMOVE,
            )
        if not state.render():
            raise GenerationError("Generator returned empty story context")

        story_context = state.dump()

        await self._scene_service.update_story_context(scene.id, story_context)
        return story_context

    def __create_prompt(
        self,
        novel: Novel,
        scene: Scene,
        characters: list[Character],
        lines: list[DialogueLine],
        state: StoryState,
    ) -> list[dict]:
        has_codex = novel.universe_id is not None
        outfit_instruction = (
            "outfit оставляй пустой — наряд персонажа задаётся каталогом Codex "
            "через outfit_tag в репликах, не выдумывай его."
            if has_codex
            else "outfit - во что одет сейчас (коротко: одежда, цвета); меняй ТОЛЬКО если "
            "персонаж явно переоделся в этой сцене, иначе оставляй пустую строку. "
            "Не переписывай уже указанную одежду другими словами."
        )
        system_prompt = {
            "role": "system",
            "content": (
                "Ты редактор интерактивной визуальной новеллы и ведёшь изложение истории, "
                "по которому будут генерироваться следующие сцены. "
                "По предыдущему изложению и диалогу новой сцены верни ТОЛЬКО изменения:\n"
                "- summary - новое краткое содержание всей истории с учётом сцены, не больше 5 предложений. "
                "Переписывай компактно, не повторяя дословно предыдущее изложение, и не пересказывай "
                "одно и то же из сцены в сцену;\n"
                "- remove_facts - номера фактов из предыдущего изложения, которые устарели, "
                "больше не важны для сюжета или поглощены новыми;\n"
                "- add_facts - новые факты из этой сцены, важные для сюжета дальше "
                "(события, решения, тайны, обещания, отношения, предметы, где находятся персонажи), "
                "каждый — одно короткое предложение до 120 символов. Факт считается дублем, если повторяет "
                "смысл существующего факта, даже другими словами — не добавляй такие. Если новый факт "
                "поглощает существующий, добавь номер поглощённого в remove_facts. "
                f"После изменений фактов должно остаться не больше {MAX_KEY_FACTS};\n"
                "- characters - только персонажи, у которых что-то изменилось или которые появились впервые: "
                f"{outfit_instruction} "
                "state - физическое и эмоциональное состояние, до 80 символов. Пустая строка — без изменений;\n"
                f"- used_phrases - до {MAX_USED_PHRASES} фраз-мотивов (2 и более слов, без имён персонажей), "
                "которые уже звучали в истории более одного раза и не должны повторяться "
                "дословно в следующих сценах.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "summary": string,
                  "remove_facts": [int],
                  "add_facts": [string],
                  "characters": [
                    {
                      "name": string,
                      "outfit": string,
                      "state": string
                    }
                  ],
                  "used_phrases": [string]
                }
                """
            ),
        }
        cast = "\n".join(
            f"- {c.name} ({c.role}{', протагонист' if c.is_protagonist else ''})"
            for c in characters
        )
        names = {c.id: c.name for c in characters}
        dialogue = "\n".join(
            f"{names.get(line.character_id, '?')}"
            f"{' (мысли)' if line.is_thought else ''}: {_short_line(line.text)}"
            for line in lines
        )
        user_content = (
            f"Название истории: {novel.title}\n"
            f"Персонажи:\n{cast}\n\n"
            f"Предыдущее изложение:\n{state.render(numbered=True) or 'нет, это первая сцена'}\n\n"
            f"Новая сцена: {scene.title}\n"
            f"Описание сцены: {scene.description}\n"
            f"Диалог сцены:\n{dialogue}"
        )
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]
