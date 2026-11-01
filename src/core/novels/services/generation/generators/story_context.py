import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import (
    Character,
    DialogueLine,
    Novel,
    Prompt,
    PromptKey,
    Scene,
)
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.prompts.catalog import (
    PromptCatalog,
    render_messages,
)
from src.core.novels.services.generation.prompts.dialogue import DialoguePromptBuilder
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE
from src.core.novels.services.generation.story_state import (
    MAX_KEY_FACTS,
    MAX_USED_PHRASES,
    MIN_FACT_AGE_TO_REMOVE,
    StoryState,
    extract_used_phrases,
    render_story_context,
)
from src.core.novels.services.generation.transactions import (
    TransactionFactory,
    noop_step,
)

# Реэкспорт чистых хелперов для обратной совместимости: их импортируют
# DialogueGenerator (extract_used_phrases), SceneContinuationService
# (render_story_context) и тесты (StoryState/extract_used_phrases/MAX_*).
__all__ = (
    "MAX_KEY_FACTS",
    "MAX_USED_PHRASES",
    "MIN_FACT_AGE_TO_REMOVE",
    "StoryContextGenerator",
    "StoryState",
    "extract_used_phrases",
    "render_story_context",
)

logger = logging.getLogger(__name__)


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
        prompt_catalog: PromptCatalog,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service
        self._scene_service = scene_service
        self._character_service = character_service
        self._dialogue_line_service = dialogue_line_service
        self._prompts = prompt_catalog

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
            template = await self._prompts.get(
                PromptKey.STORY_CONTEXT, novel.prompt_variant
            )

        # 2) LLM-фаза: без транзакции.
        state = StoryState.load(previous_context)
        prompt = self.__create_prompt(template, novel, scene, characters, lines, state)

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

    @staticmethod
    def __create_prompt(
        template: Prompt,
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

        cast = "\n".join(
            f"- {c.name} ({c.role}"
            f"{', protagonist' if c.is_protagonist else ''}"
            f"{', ' + c.gender if c.gender else ''})"
            for c in characters
        )
        names = {c.id: c.name for c in characters}
        dialogue = "\n".join(
            DialoguePromptBuilder.render_previous_line(
                line, names, narration_label="[описание]"
            )
            for line in lines
        )

        return render_messages(
            template,
            system_vars={
                "outfit_instruction": outfit_instruction,
                "max_key_facts": MAX_KEY_FACTS,
                "russian_note": RUSSIAN_OUTPUT_NOTE,
            },
            user_vars={
                "title": novel.title,
                "cast": cast,
                "previous_recap": state.render(numbered=True)
                or "none, this is the first scene",
                "scene_title": scene.title,
                "scene_description": scene.description,
                "dialogue": dialogue,
            },
        )
