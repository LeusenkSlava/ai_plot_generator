import logging

from src.core.novels.exceptions import (
    NovelFinishedError,
    NovelNotFoundError,
    SceneOrderError,
)
from src.core.novels.interfaces.generation import SceneGenerationLockProtocol
from src.core.novels.interfaces.repository import (
    DialogueLineRepositoryProtocol,
    NovelRepositoryProtocol,
    RoadmapRepositoryProtocol,
    SceneRepositoryProtocol,
)
from src.core.novels.llm_trace import llm_trace
from src.core.novels.models import Scene
from src.core.novels.services.generate.dialogue import DialogueGenerator
from src.core.novels.services.generate.scene import SceneGenerator
from src.core.novels.services.generate.story_context import (
    StoryContextGenerator,
    render_story_context,
)
from src.core.novels.services.state import NextSceneSlot, NovelState

logger = logging.getLogger(__name__)


class SceneContinuationService:
    """Догенерация новеллы: сцена с порядковым номером scene_order вместе с репликами"""

    def __init__(
        self,
        novel_repository: NovelRepositoryProtocol,
        roadmap_repository: RoadmapRepositoryProtocol,
        scene_repository: SceneRepositoryProtocol,
        dialogue_line_repository: DialogueLineRepositoryProtocol,
        scene_generator: SceneGenerator,
        dialogue_generator: DialogueGenerator,
        story_context_generator: StoryContextGenerator,
        lock: SceneGenerationLockProtocol,
    ):
        self._novels = novel_repository
        self._roadmaps = roadmap_repository
        self._scenes = scene_repository
        self._dialogue_lines = dialogue_line_repository
        self._scene_generator = scene_generator
        self._dialogue_generator = dialogue_generator
        self._story_context_generator = story_context_generator
        self._lock = lock

    async def generate(self, novel_id: int, scene_order: int) -> Scene:
        with llm_trace(f"scene_{scene_order}", novel_id=novel_id):
            return await self._generate(novel_id, scene_order)

    async def _generate(self, novel_id: int, scene_order: int) -> Scene:
        """Возвращает сцену. Вызывающий должен закоммитить транзакцию:
        advisory-блокировка держится до её конца.
        """
        if await self._novels.get_by_id(novel_id) is None:
            raise NovelNotFoundError(novel_id)

        logger.info(
            "Scene generation: start novel_id=%s scene_order=%s",
            novel_id,
            scene_order,
        )

        await self._lock.acquire(novel_id, scene_order)

        state = await self._load_state(novel_id)

        if (existing := state.scene_at(scene_order)) is not None:
            return existing

        slot = state.resolve_next_slot()
        if slot is None:
            raise NovelFinishedError(novel_id)
        if scene_order != slot.order:
            raise SceneOrderError(novel_id, scene_order, slot.order)

        scene = await self._run_pipeline(slot, state)
        return scene

    async def _load_state(self, novel_id: int) -> NovelState:
        roadmaps = await self._roadmaps.list_by_novel_id(novel_id)
        scenes = await self._scenes.list_by_novel_id(novel_id)
        lines = await self._dialogue_lines.list_by_novel_id(novel_id)
        return NovelState(roadmaps=roadmaps, scenes=scenes, dialogue_lines=lines)

    async def _run_pipeline(self, slot: NextSceneSlot, state: NovelState) -> Scene:
        story_text = render_story_context(state.last_story_context)

        scene = await self._scene_generator.generate(
            slot.roadmap.id,
            previous_scenes=state.last_scenes,
            story_context=story_text,
            order=slot.order,
        )

        await self._dialogue_generator.generate(
            scene.id,
            previous_lines=state.previous_dialogue_lines,
            story_context=story_text,
        )

        await self._story_context_generator.generate(
            scene.id, previous_context=state.last_story_context
        )
        return scene
