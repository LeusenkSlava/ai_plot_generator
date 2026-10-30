import logging

from src.core.novels.exceptions import (
    NovelFinishedError,
    NovelNotFoundError,
    SceneOrderError,
)
from src.core.novels.interfaces.repository import (
    DialogueLineRepositoryProtocol,
    NovelRepositoryProtocol,
    RoadmapRepositoryProtocol,
    SceneRepositoryProtocol,
)
from src.core.novels.llm_trace import llm_trace
from src.core.novels.models import Scene
from src.core.novels.services.generation.generators.dialogue import DialogueGenerator
from src.core.novels.services.generation.generators.scene import SceneGenerator
from src.core.novels.services.generation.generators.story_context import (
    StoryContextGenerator,
    render_story_context,
)
from src.core.novels.services.generation.state import NextSceneSlot, NovelState
from src.core.novels.services.generation.transactions import TransactionFactory

logger = logging.getLogger(__name__)


class SceneContinuationService:
    """Догенерация новеллы: сцена с порядковым номером scene_order вместе с репликами.

    Блокировка ``(novel_id, scene_order)`` держится вызывающим (use-case) на Redis,
    а генераторы сами делят работу на короткие read/write-транзакции и не держат
    соединение Postgres во время LLM-вызовов. При сбое частично созданная сцена
    удаляется каскадом (компенсация).
    """

    def __init__(
        self,
        novel_repository: NovelRepositoryProtocol,
        roadmap_repository: RoadmapRepositoryProtocol,
        scene_repository: SceneRepositoryProtocol,
        dialogue_line_repository: DialogueLineRepositoryProtocol,
        scene_generator: SceneGenerator,
        dialogue_generator: DialogueGenerator,
        story_context_generator: StoryContextGenerator,
    ):
        self._novels = novel_repository
        self._roadmaps = roadmap_repository
        self._scenes = scene_repository
        self._dialogue_lines = dialogue_line_repository
        self._scene_generator = scene_generator
        self._dialogue_generator = dialogue_generator
        self._story_context_generator = story_context_generator

    async def generate(
        self, novel_id: int, scene_order: int, *, step: TransactionFactory
    ) -> Scene:
        with llm_trace(f"scene_{scene_order}", novel_id=novel_id):
            return await self._generate(novel_id, scene_order, step=step)

    async def _generate(
        self, novel_id: int, scene_order: int, *, step: TransactionFactory
    ) -> Scene:
        """Возвращает сцену. Read-фаза коммитится отдельно (``step``)."""
        async with step():
            if await self._novels.get_by_id(novel_id) is None:
                raise NovelNotFoundError(novel_id)

            state = await self._load_state(novel_id)

            if (existing := state.scene_at(scene_order)) is not None:
                return existing

            slot = state.resolve_next_slot()
            if slot is None:
                raise NovelFinishedError(novel_id)
            if scene_order != slot.order:
                raise SceneOrderError(novel_id, scene_order, slot.order)

        return await self._run_pipeline(slot, state, step=step)

    async def _load_state(self, novel_id: int) -> NovelState:
        roadmaps = await self._roadmaps.list_by_novel_id(novel_id)
        scenes = await self._scenes.list_by_novel_id(novel_id)
        lines = await self._dialogue_lines.list_by_novel_id(novel_id)
        return NovelState(roadmaps=roadmaps, scenes=scenes, dialogue_lines=lines)

    async def _run_pipeline(
        self, slot: NextSceneSlot, state: NovelState, *, step: TransactionFactory
    ) -> Scene:
        story_text = render_story_context(state.last_story_context)

        scene: Scene | None = None
        try:
            scene = await self._scene_generator.generate(
                slot.roadmap.id,
                previous_scenes=state.last_scenes,
                story_context=story_text,
                order=slot.order,
                step=step,
            )

            if scene.needs_review:
                return scene

            await self._dialogue_generator.generate(
                scene.id,
                previous_lines=state.previous_dialogue_lines,
                story_context=story_text,
                all_lines=state.dialogue_lines,
                step=step,
            )

            # После финальной сцены контекст некому читать: его берёт только генерация
            # следующей сцены, а её не будет. Пропускаем вызов, чтобы не платить за мёртвый контекст.
            if scene.is_final_for_novel:
                return scene

            await self._story_context_generator.generate(
                scene.id, previous_context=state.last_story_context, step=step
            )
            return scene
        except Exception:
            # Компенсация: сцена уже закоммичена, а диалог/контекст не доехали —
            # удаляем её (СУБД каскадно убирает реплики и действия), чтобы ретрай
            # начал с чистого листа.
            if scene is not None:
                try:
                    async with step():
                        await self._scenes.delete(scene.id)
                except Exception:
                    logger.exception(
                        "Scene generation compensation failed for scene %s",
                        scene.id,
                    )
            raise
