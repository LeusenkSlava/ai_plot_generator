from tests.fakes.core.novel.novel_service import FakeNovelService
from tests.fakes.outbound.ai.generator import FakeGenerator
from tests.fakes.outbound.codex.client import FakeCodexService
from tests.fakes.outbound.database.repositories.character_repository import (
    FakeCharacterRepository,
)
from tests.fakes.outbound.database.repositories.dialogue_action_repository import (
    FakeDialogueActionRepository,
)
from tests.fakes.outbound.database.repositories.dialogue_line_repository import (
    FakeDialogueLineRepository,
)
from tests.fakes.outbound.database.repositories.generation_job_repository import (
    FakeGenerationJobRepository,
)
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)
from tests.fakes.outbound.database.repositories.roadmap_repository import (
    FakeRoadmapRepository,
)
from tests.fakes.outbound.database.repositories.scene_generation_lock import (
    FakeSceneGenerationLock,
)
from tests.fakes.outbound.database.repositories.scene_repository import (
    FakeSceneRepository,
)

__all__ = [
    "FakeCharacterRepository",
    "FakeCodexService",
    "FakeDialogueActionRepository",
    "FakeDialogueLineRepository",
    "FakeGenerationJobRepository",
    "FakeGenerator",
    "FakeNovelRepository",
    "FakeNovelService",
    "FakeRoadmapRepository",
    "FakeSceneGenerationLock",
    "FakeSceneRepository",
]
