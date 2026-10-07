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
from src.core.novels.services.generate.base import BaseGenerator

logger = logging.getLogger(__name__)

MAX_KEY_FACTS = 12
MAX_USED_PHRASES = 10


def _normalize(text: str) -> str:
    """Нормализация текста для сравнения фактов: регистр, пунктуация, лишние пробелы."""
    return re.sub(r"[^\wа-яё0-9]+", " ", text.lower()).strip()


@dataclass
class StoryState:
    """Изложение истории после сцены. Хранится в scenes.story_context как JSON."""

    summary: str = ""
    key_facts: list[str] = field(default_factory=list)
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
        return cls(
            summary=data.get("summary") or "",
            key_facts=list(data.get("key_facts") or []),
            characters=dict(data.get("characters") or {}),
            used_phrases=list(data.get("used_phrases") or []),
        )

    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    def apply(self, delta: dict) -> None:
        """Применяет изменения от LLM: новое summary, удалённые/добавленные факты, изменившихся персонажей."""
        if summary := (delta.get("summary") or "").strip():
            self.summary = summary
        removed = {i for i in delta.get("remove_facts") or [] if isinstance(i, int)}
        self.key_facts = [
            f for i, f in enumerate(self.key_facts, 1) if i not in removed
        ]
        self.key_facts = self.__merge_facts(
            self.key_facts, delta.get("add_facts") or []
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

    @staticmethod
    def __merge_facts(existing: list[str], added: list[str]) -> list[str]:
        """Склейка фактов без дублей: точный повтор/вложенность отбрасывается,
        а факт, поглощающий существующий, заменяет его. Самые старые уходят первыми."""
        result = list(existing)
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
            else:
                result.append(fact)
        return result[-MAX_KEY_FACTS:]

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


def render_story_context(raw: str | None) -> str | None:
    """scenes.story_context -> текст для промтов сцены и диалога."""
    return StoryState.load(raw).render() or None


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

        state = StoryState.load(previous_context)
        prompt = self.__create_prompt(novel, scene, characters, lines, state)
        state.apply(await self._generate(prompt, think=False))
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
                "- used_phrases - до 5 фраз-мотивов (2 и более слов), которые уже звучали в истории "
                "более одного раза и не должны повторяться дословно в следующих сценах.\n"
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
        cast = "\n".join(f"- {c.name} ({c.role})" for c in characters)
        names = {c.id: c.name for c in characters}
        dialogue = "\n".join(
            f"{names.get(line.character_id, '?')}: {line.text}" for line in lines
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
