import logging

from src.core.novels.llm_trace import llm_trace
from src.core.novels.models import Novel
from src.core.novels.services.generate.character import CharacterGenerator
from src.core.novels.services.generate.dialogue import DialogueGenerator
from src.core.novels.services.generate.novel import NovelGenerator
from src.core.novels.services.generate.roadmap import RoadmapGenerator
from src.core.novels.services.generate.scene import SceneGenerator
from src.core.novels.services.generate.story_context import StoryContextGenerator

logger = logging.getLogger(__name__)


class NovelCompositionService:
    def __init__(
        self,
        novel_generator: NovelGenerator,
        character_generator: CharacterGenerator,
        roadmap_generator: RoadmapGenerator,
        scene_generator: SceneGenerator,
        dialogue_generator: DialogueGenerator,
        story_context_generator: StoryContextGenerator,
    ):
        self._novel_generator = novel_generator
        self._character_generator = character_generator
        self._roadmap_generator = roadmap_generator
        self._scene_generator = scene_generator
        self._dialogue_generator = dialogue_generator
        self._story_context_generator = story_context_generator

    async def create(self, user_promt: str, universe_id: int | None = None) -> Novel:
        with llm_trace("create_novel") as trace:
            novel = await self._novel_generator.generate(
                user_promt,
                universe_id=universe_id,
            )
            trace.bind(novel.id)
            await self._character_generator.generate(novel.id)
            roadmap = await self._roadmap_generator.generate(novel.id)

            first_step = roadmap[0]
            scene = await self._scene_generator.generate(first_step.id)
            await self._dialogue_generator.generate(scene.id)
            # Для первой сцены изложения ещё нет — собираем его только из её диалога
            await self._story_context_generator.generate(scene.id)

            return novel
