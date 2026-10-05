from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.codex.services import CodexService
from src.core.novels.services.composition import NovelCompositionService
from src.core.novels.services.continuation import SceneContinuationService
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generate import (
    CharacterGenerator,
    DialogueGenerator,
    NovelGenerator,
    RoadmapGenerator,
    SceneGenerator,
    StoryContextGenerator,
)
from src.core.novels.use_cases import (
    GenerateNovelUseCase,
    GenerateSceneUseCase,
)
from src.outbound.ai.client import build_deepseek_client
from src.outbound.ai.deepseek_client import DeepSeekGenerator
from src.outbound.codex.client import build_codex_client
from src.outbound.codex.codex_client import HttpCodexClient
from src.outbound.database.repositories.generation_job_repository import (
    GenerationJobRepository,
)
from src.outbound.database.repositories.novel_repository import (
    CharacterRepository,
    DialogueLineRepository,
    NovelRepository,
    RoadmapRepository,
    SceneRepository,
)
from src.outbound.database.repositories.scene_generation_lock import (
    SceneGenerationLock,
)


@dataclass(frozen=True, slots=True)
class NovelRepositories:
    novel: NovelRepository
    character: CharacterRepository
    roadmap: RoadmapRepository
    scene: SceneRepository
    dialogue_line: DialogueLineRepository


def build_novel_repositories(session: AsyncSession) -> NovelRepositories:
    return NovelRepositories(
        novel=NovelRepository(session),
        character=CharacterRepository(session),
        roadmap=RoadmapRepository(session),
        scene=SceneRepository(session),
        dialogue_line=DialogueLineRepository(session),
    )


@dataclass(frozen=True, slots=True)
class NovelDomainServices:
    novel: NovelService
    character: CharacterService
    roadmap: RoadmapService
    scene: SceneService
    dialogue_line: DialogueLineService


def build_novel_domain_services(
    repos: NovelRepositories,
) -> NovelDomainServices:
    return NovelDomainServices(
        novel=NovelService(repos.novel),
        character=CharacterService(repos.character),
        roadmap=RoadmapService(repos.roadmap),
        scene=SceneService(repos.scene),
        dialogue_line=DialogueLineService(repos.dialogue_line),
    )


@dataclass(frozen=True, slots=True)
class NovelGenerators:
    novel: NovelGenerator
    character: CharacterGenerator
    roadmap: RoadmapGenerator
    scene: SceneGenerator
    dialogue: DialogueGenerator
    story_context: StoryContextGenerator


def build_novel_generators(
    services: NovelDomainServices,
) -> NovelGenerators:
    generator = DeepSeekGenerator(client=build_deepseek_client())
    codex_service = CodexService(HttpCodexClient(build_codex_client()))

    return NovelGenerators(
        novel=NovelGenerator(
            novel_service=services.novel,
            codex_service=codex_service,
            generator=generator,
        ),
        character=CharacterGenerator(
            novel_service=services.novel,
            character_service=services.character,
            codex_service=codex_service,
            generator=generator,
        ),
        roadmap=RoadmapGenerator(
            novel_service=services.novel,
            roadmap_service=services.roadmap,
            generator=generator,
        ),
        scene=SceneGenerator(
            novel_service=services.novel,
            roadmap_service=services.roadmap,
            scene_service=services.scene,
            generator=generator,
        ),
        dialogue=DialogueGenerator(
            novel_service=services.novel,
            codex_service=codex_service,
            scene_service=services.scene,
            roadmap_service=services.roadmap,
            character_service=services.character,
            dialogue_line_service=services.dialogue_line,
            generator=generator,
        ),
        story_context=StoryContextGenerator(
            novel_service=services.novel,
            roadmap_service=services.roadmap,
            scene_service=services.scene,
            character_service=services.character,
            dialogue_line_service=services.dialogue_line,
            generator=generator,
        ),
    )


def build_novel_composition_service(
    session: AsyncSession,
) -> NovelCompositionService:
    repos = build_novel_repositories(session)
    services = build_novel_domain_services(repos)
    generators = build_novel_generators(services)

    return NovelCompositionService(
        novel_generator=generators.novel,
        character_generator=generators.character,
        roadmap_generator=generators.roadmap,
        scene_generator=generators.scene,
        dialogue_generator=generators.dialogue,
        story_context_generator=generators.story_context,
    )


def build_scene_continuation_service(
    session: AsyncSession,
) -> SceneContinuationService:
    repos = build_novel_repositories(session)
    services = build_novel_domain_services(repos)
    generators = build_novel_generators(services)

    return SceneContinuationService(
        novel_repository=repos.novel,
        roadmap_repository=repos.roadmap,
        scene_repository=repos.scene,
        dialogue_line_repository=repos.dialogue_line,
        scene_generator=generators.scene,
        dialogue_generator=generators.dialogue,
        story_context_generator=generators.story_context,
        lock=SceneGenerationLock(session),
    )


def build_generate_novel_use_case(
    session: AsyncSession,
) -> GenerateNovelUseCase:
    return GenerateNovelUseCase(
        jobs_repo=GenerationJobRepository(session),
        composition_service=build_novel_composition_service(session),
    )


def build_generate_scene_use_case(
    session: AsyncSession,
) -> GenerateSceneUseCase:
    return GenerateSceneUseCase(
        jobs_repo=GenerationJobRepository(session),
        continuation_service=build_scene_continuation_service(session),
    )
