import json
import logging
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


@dataclass
class StoryState:
    """Изложение истории после сцены. Хранится в scenes.story_context как JSON."""

    summary: str = ""
    key_facts: list[str] = field(default_factory=list)
    # имя персонажа -> {"outfit": ..., "state": ...}
    characters: dict[str, dict[str, str]] = field(default_factory=dict)

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
        self.key_facts += [
            f.strip() for f in delta.get("add_facts") or [] if f and f.strip()
        ]
        # Страховка от разрастания: самые старые факты уходят первыми
        self.key_facts = self.key_facts[-MAX_KEY_FACTS:]
        for c in delta.get("characters") or []:
            if not c.get("name"):
                continue
            current = self.characters.setdefault(c["name"], {})
            for key in ("outfit", "state"):
                if value := (c.get(key) or "").strip():
                    current[key] = value

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
        state.apply(await self._generate(prompt))
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
        system_prompt = {
            "role": "system",
            "content": (
                "Ты редактор интерактивной визуальной новеллы и ведёшь изложение истории, "
                "по которому будут генерироваться следующие сцены. "
                "По предыдущему изложению и диалогу новой сцены верни ТОЛЬКО изменения:\n"
                "- summary - новое краткое содержание всей истории с учётом сцены, не больше 5 предложений;\n"
                "- remove_facts - номера фактов из предыдущего изложения, которые устарели, "
                "больше не важны для сюжета или поглощены новыми;\n"
                "- add_facts - новые факты из этой сцены, важные для сюжета дальше "
                "(события, решения, тайны, обещания, отношения, предметы, где находятся персонажи), "
                "каждый — одно короткое предложение до 120 символов. Не повторяй уже существующие факты. "
                f"После изменений фактов должно остаться не больше {MAX_KEY_FACTS};\n"
                "- characters - только персонажи, у которых что-то изменилось или которые появились впервые: "
                "outfit - во что одет сейчас (коротко: одежда, цвета; сохраняется, пока персонаж явно не переоделся, "
                "если ещё не упоминалась — придумай подходящую), "
                "state - физическое и эмоциональное состояние, до 80 символов. Пустая строка — без изменений.\n"
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
                  ]
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
