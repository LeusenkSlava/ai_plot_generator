import logging

from src.core.novels.models import Novel
from src.core.novels.services.generate.character import CharacterGenerator
from src.core.novels.services.generate.dialogue import DialogueGenerator
from src.core.novels.services.generate.novel import NovelGenerator
from src.core.novels.services.generate.roadmap import RoadmapGenerator
from src.core.novels.services.generate.scene import SceneGenerator

logger = logging.getLogger(__name__)


class NovelCompositionService:
    def __init__(
        self,
        novel_generator: NovelGenerator,
        character_generator: CharacterGenerator,
        roadmap_generator: RoadmapGenerator,
        scene_generator: SceneGenerator,
        dialogue_generator: DialogueGenerator,
    ):
        self._novel_generator = novel_generator
        self._character_generator = character_generator
        self._roadmap_generator = roadmap_generator
        self._scene_generator = scene_generator
        self._dialogue_generator = dialogue_generator

    async def create(self, user_promt: str) -> Novel:
        logger.info(f"Creating novel for prompt: {user_promt}")
        novel = await self._novel_generator.generate(user_promt)
        await self._character_generator.generate(novel.id)
        roadmap = await self._roadmap_generator.generate(novel.id)

        first_step = roadmap[0]
        scene = await self._scene_generator.generate(first_step.id)
        await self._dialogue_generator.generate(scene.id)

        return novel
