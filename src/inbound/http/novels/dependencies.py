from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.playback import NovelPlaybackService
from src.main.config.settings import settings
from src.outbound.cache.client import build_redis_client
from src.outbound.cache.redis_lock import RedisSceneLock
from src.outbound.database.dependencies import get_db_session
from src.outbound.database.repositories.novel_repository import (
    CharacterRepository,
    DialogueActionRepository,
    DialogueLineRepository,
    NovelRepository,
    RoadmapRepository,
    SceneRepository,
)


def get_novel_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NovelRepository:
    return NovelRepository(session)


def get_character_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CharacterRepository:
    return CharacterRepository(session)


def get_roadmap_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RoadmapRepository:
    return RoadmapRepository(session)


def get_scene_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SceneRepository:
    return SceneRepository(session)


def get_dialogue_line_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DialogueLineRepository:
    return DialogueLineRepository(session)


def get_dialogue_action_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DialogueActionRepository:
    return DialogueActionRepository(session)


def get_scene_generation_lock() -> RedisSceneLock:
    return RedisSceneLock(
        build_redis_client(),
        ttl_s=settings.generation.SCENE_LOCK_TTL_S,
        acquire_timeout_s=settings.generation.SCENE_LOCK_ACQUIRE_TIMEOUT_S,
        poll_interval_s=settings.generation.IN_PROGRESS_POLL_INTERVAL_S,
    )


def get_novel_service(
    repository: Annotated[NovelRepository, Depends(get_novel_repository)],
) -> NovelService:
    return NovelService(repository)


def get_character_service(
    repository: Annotated[CharacterRepository, Depends(get_character_repository)],
) -> CharacterService:
    return CharacterService(repository)


def get_roadmap_service(
    repository: Annotated[RoadmapRepository, Depends(get_roadmap_repository)],
) -> RoadmapService:
    return RoadmapService(repository)


def get_scene_service(
    repository: Annotated[SceneRepository, Depends(get_scene_repository)],
) -> SceneService:
    return SceneService(repository)


def get_dialogue_line_service(
    repository: Annotated[
        DialogueLineRepository, Depends(get_dialogue_line_repository)
    ],
) -> DialogueLineService:
    return DialogueLineService(repository)


def get_novel_playback_service(
    novel_repository: Annotated[NovelRepository, Depends(get_novel_repository)],
    roadmap_repository: Annotated[RoadmapRepository, Depends(get_roadmap_repository)],
    scene_repository: Annotated[SceneRepository, Depends(get_scene_repository)],
    dialogue_line_repository: Annotated[
        DialogueLineRepository, Depends(get_dialogue_line_repository)
    ],
    character_repository: Annotated[
        CharacterRepository, Depends(get_character_repository)
    ],
    lock: Annotated[RedisSceneLock, Depends(get_scene_generation_lock)],
) -> NovelPlaybackService:
    return NovelPlaybackService(
        novel_repository=novel_repository,
        roadmap_repository=roadmap_repository,
        scene_repository=scene_repository,
        dialogue_line_repository=dialogue_line_repository,
        character_repository=character_repository,
        lock=lock,
    )
