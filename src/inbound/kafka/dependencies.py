from sqlalchemy.ext.asyncio import AsyncSession

from src.core.codex.services import CodexService
from src.core.novels.services.composition import NovelCompositionService
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generate.character import CharacterGenerator
from src.core.novels.services.generate.dialogue import DialogueGenerator
from src.core.novels.services.generate.novel import NovelGenerator
from src.core.novels.services.generate.roadmap import RoadmapGenerator
from src.core.novels.services.generate.scene import SceneGenerator
from src.outbound.ai.client import build_deepseek_client
from src.outbound.ai.codex_agent import CodexResearcher
from src.outbound.ai.deepseek_client import DeepSeekGenerator
from src.outbound.codex.client import build_codex_client
from src.outbound.codex.codex_client import HttpCodexClient
from src.outbound.database.repositories.novel_repository import (
    CharacterRepository,
    DialogueLineRepository,
    NovelRepository,
    RoadmapRepository,
    SceneRepository,
)


def build_novel_composition_service(session: AsyncSession) -> NovelCompositionService:
    novel_repository = NovelRepository(session)
    character_repository = CharacterRepository(session)
    roadmap_repository = RoadmapRepository(session)
    scene_repository = SceneRepository(session)
    dialogue_line_repository = DialogueLineRepository(session)

    novel_service = NovelService(novel_repository)
    character_service = CharacterService(character_repository)
    roadmap_service = RoadmapService(roadmap_repository)
    scene_service = SceneService(scene_repository)
    dialogue_line_service = DialogueLineService(dialogue_line_repository)

    generator = DeepSeekGenerator(client=build_deepseek_client())
    codex_service = CodexService(HttpCodexClient(build_codex_client()))
    novel_generator = NovelGenerator(generator=generator, novel_service=novel_service)
    character_generator = CharacterGenerator(
        novel_service=novel_service,
        character_service=character_service,
        codex_service=codex_service,
        generator=generator,
    )
    roadmap_generator = RoadmapGenerator(
        novel_service=novel_service,
        roadmap_service=roadmap_service,
        generator=generator,
    )
    scene_generator = SceneGenerator(
        novel_service=novel_service,
        roadmap_service=roadmap_service,
        scene_service=scene_service,
        generator=generator,
    )
    dialogue_generator = DialogueGenerator(
        novel_service=novel_service,
        codex_service=codex_service,
        scene_service=scene_service,
        roadmap_service=roadmap_service,
        character_service=character_service,
        dialogue_line_service=dialogue_line_service,
        generator=generator,
    )

    return NovelCompositionService(
        novel_generator=novel_generator,
        character_generator=character_generator,
        roadmap_generator=roadmap_generator,
        scene_generator=scene_generator,
        dialogue_generator=dialogue_generator,
        codex_researcher=build_codex_researcher(),
    )


def build_codex_researcher() -> CodexResearcher:
    codex_service = CodexService(HttpCodexClient(build_codex_client()))
    return CodexResearcher(build_deepseek_client(), codex_service)
