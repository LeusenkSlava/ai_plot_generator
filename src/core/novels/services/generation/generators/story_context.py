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
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE
from src.core.novels.services.generation.transactions import (
    TransactionFactory,
    noop_step,
)

logger = logging.getLogger(__name__)

MAX_KEY_FACTS = 12
# Максимум повторяющихся фраз (n-грамм), которые код кладёт в «не повторять дословно».
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


class StoryContextGenerator(BaseGenerator):
    """Изложение истории после сцены.

    LLM возвращает только изменения относительно предыдущего изложения
    (добавленные/удалённые факты, изменившихся персонажей), склеиваем их в коде.
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

    async def generate(
        self,
        scene_id: int,
        previous_context: str | None = None,
        *,
        step: TransactionFactory = noop_step,
    ) -> str:
        # 1) Read-фаза: короткая транзакция.
        async with step():
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

        # 2) LLM-фаза: без транзакции.
        state = StoryState.load(previous_context)
        prompt = self.__create_prompt(novel, scene, characters, lines, state)

        # Один вызов LLM: добавление/удаление фактов + изменившиеся персонажи,
        # склейка фактов в коде. Смысловая дедупликация фактов и LLM-проверка
        # противоречий убраны как нерентабельные: проверка противоречий ловила
        # ~1 случай на прогон при 52 микровызовах, а дубли гасит __merge_facts
        # (точное/вложенное совпадение).
        delta = await self._generate(prompt, think=False)
        delta = dict(delta)

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

        # 3) Write-фаза: короткая транзакция только на запись.
        async with step():
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
            "leave outfit empty — the character's outfit is set by the Codex catalog "
            "via outfit_tag in the lines; do not invent it."
            if has_codex
            else "outfit - what they are wearing now (briefly: clothes, colors); change it ONLY if "
            "the character clearly changed clothes in this scene, otherwise leave an empty string. "
            "Do not rewrite already-specified clothes in other words."
        )
        system_prompt = {
            "role": "system",
            "content": (
                "You are the editor of an interactive visual novel and maintain the story recap "
                "from which the following scenes will be generated. "
                "Based on the previous recap and the new scene's dialogue, return ONLY the changes:\n"
                "- remove_facts - the numbers of facts from the previous recap that are outdated, "
                "no longer important to the plot, or absorbed by new ones;\n"
                "- add_facts - new facts from this scene that matter for the plot going forward "
                "(events, decisions, secrets, promises, relationships, objects, where characters are), "
                "each a single short sentence up to 120 characters. A fact counts as a duplicate if it repeats "
                "the meaning of an existing fact, even in different words — do not add such facts. If a new fact "
                "absorbs an existing one, add the number of the absorbed one to remove_facts. "
                f"No more than {MAX_KEY_FACTS} facts should remain after the changes;\n"
                "- characters - only characters for whom something changed or who appear for the first time: "
                f"{outfit_instruction} "
                "state - physical and emotional state, up to 80 characters. Empty string means no changes.\n"
                "Answer STRICTLY as JSON matching this schema:\n"
                """
                {
                  "remove_facts": [int],
                  "add_facts": [string],
                  "characters": [
                    {
                      "name": string,
                      "outfit": string,
                      "state": string
                    }
                  ]
                }
                """
            ),
        }
        cast = "\n".join(
            f"- {c.name} ({c.role}"
            f"{', protagonist' if c.is_protagonist else ''}"
            f"{', ' + c.gender if c.gender else ''})"
            for c in characters
        )
        names = {c.id: c.name for c in characters}
        dialogue = "\n".join(
            f"{names.get(line.character_id, '?')}"
            f"{' (thoughts)' if line.is_thought else ''}: {_short_line(line.text)}"
            for line in lines
        )
        user_content = (
            f"Story title: {novel.title}\n"
            f"Characters:\n{cast}\n\n"
            f"Previous recap:\n{state.render(numbered=True) or 'none, this is the first scene'}\n\n"
            f"New scene: {scene.title}\n"
            f"Scene description: {scene.description}\n"
            f"Scene dialogue:\n{dialogue}"
        )
        system_prompt["content"] += f"\n{RUSSIAN_OUTPUT_NOTE}"
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]
