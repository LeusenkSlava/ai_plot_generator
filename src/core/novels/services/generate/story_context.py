import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces import GeneratorProtocol
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


class StoryContextGenerator(BaseGenerator):
    """Изложение истории после сцены.

    Пересобирается целиком из предыдущего изложения и реплик новой сцены, чтобы не разрастаться,
    и сохраняется в сцену. Генерация следующей сцены берёт изложение предыдущей.
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

        prompt = self.__create_prompt(novel, scene, characters, lines, previous_context)
        data = await self._generate(prompt)

        story_context = self.__format(data)
        if not story_context:
            raise GenerationError("Generator returned empty story context")

        await self._scene_service.update_story_context(scene.id, story_context)
        return story_context

    @staticmethod
    def __format(data: dict) -> str:
        """JSON от LLM -> текст изложения, который подставляется в промты следующих генераций."""
        parts = []
        if summary := (data.get("summary") or "").strip():
            parts.append(f"Краткое содержание:\n{summary}")
        if key_facts := [f for f in data.get("key_facts") or [] if f]:
            parts.append("Важные сюжетные факты:\n" + "\n".join(f"- {f}" for f in key_facts))
        characters = [c for c in data.get("characters") or [] if c.get("name")]
        if characters:
            parts.append(
                "Состояние персонажей:\n"
                + "\n".join(
                    f"- {c['name']}: одежда — {c.get('outfit') or 'не указана'}; "
                    f"состояние — {c.get('state') or 'не указано'}"
                    for c in characters
                )
            )
        return "\n\n".join(parts)

    def __create_prompt(
        self,
        novel: Novel,
        scene: Scene,
        characters: list[Character],
        lines: list[DialogueLine],
        previous_context: str | None,
    ) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "Ты редактор интерактивной визуальной новеллы и ведёшь изложение истории, "
                "по которому будут генерироваться следующие сцены. "
                "На основе предыдущего изложения и диалога новой сцены составь НОВОЕ изложение целиком: "
                "объедини старое с событиями новой сцены, сократи несущественные детали, "
                "но обязательно сохрани всё, что важно для сюжета дальше: "
                "события, решения, раскрытые тайны, обещания, отношения между персонажами, "
                "полученные и потерянные предметы, где сейчас находятся персонажи. "
                "Изложение не должно разрастаться: summary — не больше 10 предложений, "
                "key_facts — не больше 15 пунктов, устаревшие факты убирай.\n"
                "Для каждого персонажа, появлявшегося в истории, укажи:\n"
                "- outfit - во что он одет сейчас, конкретно (одежда, цвета, аксессуары). "
                "Одежда сохраняется между сценами, пока в истории явно не сказано, что персонаж переоделся. "
                "Если одежда ещё не упоминалась - придумай подходящую сцене и зафиксируй её;\n"
                "- state - физическое и эмоциональное состояние (ранения, усталость, настроение).\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "summary": string,
                  "key_facts": [string],
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
        dialogue = "\n".join(f"{names.get(line.character_id, '?')}: {line.text}" for line in lines)
        user_content = (
            f"Название истории: {novel.title}\n"
            f"Описание: {novel.description}\n"
            f"Персонажи:\n{cast}\n\n"
            f"Предыдущее изложение:\n{previous_context or 'нет, это первая сцена'}\n\n"
            f"Новая сцена: {scene.title}\n"
            f"Описание сцены: {scene.description}\n"
            f"Диалог сцены:\n{dialogue}"
        )
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]
