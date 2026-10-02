from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.codex.services import CodexService
from src.core.novels.services.continuation import NovelContinuationService
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generate.dialogue import DialogueGenerator
from src.core.novels.services.generate.scene import SceneGenerator
from src.core.novels.services.playback import NovelPlaybackService
from src.outbound.ai.deepseek_client import DeepSeekGenerator
from src.outbound.ai.dependencies import get_deepseek_generator
from src.outbound.codex.dependencies import get_codex_service
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


def get_scene_generator(
    novel_service: Annotated[NovelService, Depends(get_novel_service)],
    roadmap_service: Annotated[RoadmapService, Depends(get_roadmap_service)],
    scene_service: Annotated[SceneService, Depends(get_scene_service)],
    generator: Annotated[DeepSeekGenerator, Depends(get_deepseek_generator)],
) -> SceneGenerator:
    return SceneGenerator(
        novel_service=novel_service,
        roadmap_service=roadmap_service,
        scene_service=scene_service,
        generator=generator,
    )


def get_dialogue_generator(
    novel_service: Annotated[NovelService, Depends(get_novel_service)],
    scene_service: Annotated[SceneService, Depends(get_scene_service)],
    roadmap_service: Annotated[RoadmapService, Depends(get_roadmap_service)],
    character_service: Annotated[CharacterService, Depends(get_character_service)],
    dialogue_line_service: Annotated[
        DialogueLineService, Depends(get_dialogue_line_service)
    ],
    codex_service: Annotated[CodexService, Depends(get_codex_service)],
    generator: Annotated[DeepSeekGenerator, Depends(get_deepseek_generator)],
) -> DialogueGenerator:
    return DialogueGenerator(
        novel_service=novel_service,
        codex_service=codex_service,
        scene_service=scene_service,
        roadmap_service=roadmap_service,
        character_service=character_service,
        dialogue_line_service=dialogue_line_service,
        generator=generator,
    )


def get_novel_continuation_service(
    roadmap_service: Annotated[RoadmapService, Depends(get_roadmap_service)],
    scene_service: Annotated[SceneService, Depends(get_scene_service)],
    scene_generator: Annotated[SceneGenerator, Depends(get_scene_generator)],
    dialogue_generator: Annotated[DialogueGenerator, Depends(get_dialogue_generator)],
) -> NovelContinuationService:
    return NovelContinuationService(
        roadmap_service=roadmap_service,
        scene_service=scene_service,
        scene_generator=scene_generator,
        dialogue_generator=dialogue_generator,
    )


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
    continuation_service: Annotated[
        NovelContinuationService, Depends(get_novel_continuation_service)
    ],
) -> NovelPlaybackService:
    return NovelPlaybackService(
        novel_repository=novel_repository,
        roadmap_repository=roadmap_repository,
        scene_repository=scene_repository,
        dialogue_line_repository=dialogue_line_repository,
        character_repository=character_repository,
        continuation_service=continuation_service,
    )
