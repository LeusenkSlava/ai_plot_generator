from dataclasses import dataclass

from src.core.novels.models import DialogueLine, Roadmap, Scene

PREVIOUS_SCENES_LIMIT = 5
PREVIOUS_LINES_LIMIT = 4


@dataclass(frozen=True, slots=True)
class NextSceneSlot:
    """Куда попадёт следующая сцена: сквозной порядок + шаг роадмапа."""

    order: int
    roadmap: Roadmap


def resolve_next_slot(
    roadmaps: list[Roadmap], scenes: list[Scene]
) -> NextSceneSlot | None:
    """Следующий слот генерации или None, если роадмап пройден.

    Чистая функция: используется и NovelState (генерация), и NovelPlaybackService
    (определение статуса воспроизведения), поэтому не привязана к NovelState.
    """
    scenes_by_roadmap: dict[int, int] = {}
    for scene in scenes:
        scenes_by_roadmap[scene.roadmap_id] = (
            scenes_by_roadmap.get(scene.roadmap_id, 0) + 1
        )
    for roadmap in roadmaps:
        if scenes_by_roadmap.get(roadmap.id, 0) < max(roadmap.scenes_count, 1):
            return NextSceneSlot(order=len(scenes) + 1, roadmap=roadmap)
    return None


class NovelState:
    """Иммутабельный снапшот roadmaps/scenes/lines на момент чтения.

    Используется SceneContinuationService: помимо следующего слота, даёт
    контекст для LLM (last_scenes, last_story_context, previous_dialogue_lines).
    """

    __slots__ = ("_dialogue_lines", "_roadmaps", "_scenes")

    def __init__(
        self,
        roadmaps: list[Roadmap],
        scenes: list[Scene],
        dialogue_lines: list[DialogueLine],
    ) -> None:
        self._roadmaps = roadmaps
        self._scenes = sorted(scenes, key=lambda s: s.order)
        self._dialogue_lines = dialogue_lines

    @property
    def scenes(self) -> list[Scene]:
        return self._scenes

    @property
    def last_scenes(self) -> list[Scene]:
        return self._scenes[-PREVIOUS_SCENES_LIMIT:]

    def scene_at(self, order: int) -> Scene | None:
        return next((s for s in self._scenes if s.order == order), None)

    def resolve_next_slot(self) -> NextSceneSlot | None:
        """Делегат в свободную функцию — чтобы вызывающему не тащить два списка."""
        return resolve_next_slot(self._roadmaps, self._scenes)

    @property
    def last_story_context(self) -> str | None:
        for scene in reversed(self._scenes):
            if scene.story_context:
                return scene.story_context
        return None

    @property
    def previous_dialogue_lines(self) -> list[DialogueLine]:
        return self._dialogue_lines[-PREVIOUS_LINES_LIMIT:]
