from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.codex.services import CodexService
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.assets import SceneAssetService
from src.core.novels.services.generation.composition import NovelCompositionService
from src.core.novels.services.generation.continuation import SceneContinuationService
from src.core.novels.services.generation.generators import (
    CharacterGenerator,
    DialogueGenerator,
    NovelGenerator,
    RoadmapGenerator,
    SceneGenerator,
    StoryContextGenerator,
)
from src.core.novels.services.generation.generators.dialogue_repair import (
    DialogueRepairService,
)
from src.core.novels.services.generation.generators.scene_roadmap_validator import (
    SceneRoadmapValidator,
)
from src.core.novels.use_cases import (
    GenerateNovelUseCase,
    GenerateSceneUseCase,
)
from src.main.config.settings import settings
from src.outbound.ai.client import build_deepseek_client
from src.outbound.ai.deepseek_client import DeepSeekGenerator
from src.outbound.cache.client import build_redis_client
from src.outbound.cache.redis_cache import RedisCache
from src.outbound.cache.redis_lock import RedisJobLock, RedisSceneLock
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
    client = build_deepseek_client()

    # «Творческие» шаги (замысел новеллы, роадмап и сцены) — на более мощной
    # pro-модели, остальные структурированные шаги — на дефолтной flash-модели.
    novel_generator = DeepSeekGenerator(
        client=client,
        temperature=settings.deepseek.TEMPERATURE,
        model=settings.deepseek.NOVEL_MODEL,
    )
    roadmap_generator = DeepSeekGenerator(
        client=client,
        temperature=settings.deepseek.TEMPERATURE,
        model=settings.deepseek.ROADMAP_MODEL,
    )
    scene_generator = DeepSeekGenerator(
        client=client,
        temperature=settings.deepseek.TEMPERATURE,
        model=settings.deepseek.SCENE_MODEL,
    )
    generator = DeepSeekGenerator(
        client=client,
        temperature=settings.deepseek.TEMPERATURE,
        model=settings.deepseek.MODEL,
    )
    codex_service = CodexService(
        HttpCodexClient(
            build_codex_client(),
            cache=RedisCache(build_redis_client()),
            get_ttl_s=settings.redis.CODEX_TTL_S,
            match_ttl_s=settings.redis.CODEX_MATCH_TTL_S,
        )
    )
    scene_assets = SceneAssetService(codex_service)
    repair = DialogueRepairService(generator=generator, scene_assets=scene_assets)

    return NovelGenerators(
        novel=NovelGenerator(
            novel_service=services.novel,
            codex_service=codex_service,
            generator=novel_generator,
            reasoning_effort=settings.deepseek.NOVEL_REASONING_EFFORT,
        ),
        character=CharacterGenerator(
            novel_service=services.novel,
            character_service=services.character,
            codex_service=codex_service,
            generator=generator,
            reasoning_effort=settings.deepseek.CHARACTER_REASONING_EFFORT,
            think=settings.deepseek.CHARACTER_THINK,
        ),
        roadmap=RoadmapGenerator(
            novel_service=services.novel,
            roadmap_service=services.roadmap,
            character_service=services.character,
            codex_service=codex_service,
            generator=roadmap_generator,
            reasoning_effort=settings.deepseek.ROADMAP_REASONING_EFFORT,
            think=settings.deepseek.ROADMAP_THINK,
        ),
        scene=SceneGenerator(
            novel_service=services.novel,
            roadmap_service=services.roadmap,
            scene_service=services.scene,
            character_service=services.character,
            generator=scene_generator,
            # Валидатор сцены — дешёвая смысловая сверка со структурированным
            # JSON-ответом; оставляем на flash, чтобы не жечь pro на проверки.
            validator=SceneRoadmapValidator(generator=generator),
            max_validation_retries=settings.deepseek.SCENE_VALIDATION_RETRIES,
        ),
        dialogue=DialogueGenerator(
            novel_service=services.novel,
            scene_assets=scene_assets,
            scene_service=services.scene,
            roadmap_service=services.roadmap,
            character_service=services.character,
            dialogue_line_service=services.dialogue_line,
            generator=generator,
            reasoning_effort=settings.deepseek.DIALOGUE_REASONING_EFFORT,
            think=settings.deepseek.DIALOGUE_THINK,
            temperature=settings.deepseek.DIALOGUE_TEMPERATURE,
            repair=repair,
            max_validation_retries=settings.deepseek.DIALOGUE_VALIDATION_RETRIES,
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


def _build_repos_services_generators(
    session: AsyncSession,
) -> tuple[NovelRepositories, NovelDomainServices, NovelGenerators]:
    repos = build_novel_repositories(session)
    services = build_novel_domain_services(repos)
    generators = build_novel_generators(services)
    return repos, services, generators


def build_generate_novel_use_case(
    session: AsyncSession,
) -> GenerateNovelUseCase:
    repos, _services, generators = _build_repos_services_generators(session)

    composition = NovelCompositionService(
        novel_generator=generators.novel,
        character_generator=generators.character,
        roadmap_generator=generators.roadmap,
        scene_generator=generators.scene,
        dialogue_generator=generators.dialogue,
        story_context_generator=generators.story_context,
    )

    return GenerateNovelUseCase(
        jobs_repo=GenerationJobRepository(session),
        novel_repository=repos.novel,
        composition_service=composition,
        lock=RedisJobLock(
            build_redis_client(),
            ttl_s=settings.generation.JOB_LOCK_TTL_S,
        ),
        in_progress_poll_interval_s=settings.generation.IN_PROGRESS_POLL_INTERVAL_S,
        in_progress_timeout_s=settings.generation.IN_PROGRESS_TIMEOUT_S,
    )


def build_generate_scene_use_case(
    session: AsyncSession,
) -> GenerateSceneUseCase:
    repos, _services, generators = _build_repos_services_generators(session)

    continuation = SceneContinuationService(
        novel_repository=repos.novel,
        roadmap_repository=repos.roadmap,
        scene_repository=repos.scene,
        dialogue_line_repository=repos.dialogue_line,
        scene_generator=generators.scene,
        dialogue_generator=generators.dialogue,
        story_context_generator=generators.story_context,
    )

    return GenerateSceneUseCase(
        jobs_repo=GenerationJobRepository(session),
        continuation_service=continuation,
        lock=RedisSceneLock(
            build_redis_client(),
            ttl_s=settings.generation.SCENE_LOCK_TTL_S,
            acquire_timeout_s=settings.generation.SCENE_LOCK_ACQUIRE_TIMEOUT_S,
            poll_interval_s=settings.generation.IN_PROGRESS_POLL_INTERVAL_S,
        ),
    )
