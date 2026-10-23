from src.core.novels.services.playback import NovelPlaybackService
from tests.factories import dialogue_line_domain, scene_domain
from tests.fakes.outbound.database.repositories.character_repository import (
    FakeCharacterRepository,
)
from tests.fakes.outbound.database.repositories.dialogue_line_repository import (
    FakeDialogueLineRepository,
)
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)
from tests.fakes.outbound.database.repositories.roadmap_repository import (
    FakeRoadmapRepository,
)
from tests.fakes.outbound.database.repositories.scene_repository import (
    FakeSceneRepository,
)
from tests.fakes.outbound.database.repositories.scene_generation_lock import (
    FakeSceneGenerationLock,
)


def _service(scene_repo: FakeSceneRepository | None = None) -> NovelPlaybackService:
    return NovelPlaybackService(
        novel_repository=FakeNovelRepository(),
        roadmap_repository=FakeRoadmapRepository(),
        scene_repository=scene_repo or FakeSceneRepository(),
        dialogue_line_repository=FakeDialogueLineRepository(),
        character_repository=FakeCharacterRepository(),
        lock=FakeSceneGenerationLock(),
    )


class TestExcludeReviewLines:
    async def test_drops_lines_from_review_scenes(self):
        """Реплики сцены с needs_review не показываются игроку."""
        scene_repo = FakeSceneRepository()
        review_scene = await scene_repo.add(
            scene_domain(roadmap_id=1, order=1, needs_review=True)
        )
        ok_scene = await scene_repo.add(scene_domain(roadmap_id=1, order=2))
        lines = [
            dialogue_line_domain(id=1, scene_id=review_scene.id, order=1),
            dialogue_line_domain(id=2, scene_id=ok_scene.id, order=2),
        ]

        result = await _service(scene_repo)._exclude_review_lines(1, lines)

        assert [line.id for line in result] == [2]

    async def test_keeps_all_when_no_review_scenes(self):
        """Без needs_review-сцен реплики возвращаются без изменений."""
        scene_repo = FakeSceneRepository()
        await scene_repo.add(scene_domain(roadmap_id=1, order=1))
        lines = [dialogue_line_domain(id=1, scene_id=1, order=1)]

        result = await _service(scene_repo)._exclude_review_lines(1, lines)

        assert [line.id for line in result] == [1]
