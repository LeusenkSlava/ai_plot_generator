from dataclasses import dataclass

from src.core.novels.models import DialogueLine, Roadmap, Scene

PREVIOUS_SCENES_LIMIT = 5
PREVIOUS_LINES_LIMIT = 4


@dataclass(frozen=True, slots=True)
class NextSceneSlot:
    """Куда попадёт следующая сцена: сквозной порядок + шаг роадмапа."""

    order: int
    roadmap: Roadmap


def is_step_closed(roadmap: Roadmap, scenes: list[Scene]) -> bool:
    """Явный признак закрытия шага роадмапа.

    Шаг закрыт, только когда все его сцены сгенерированы И прошли смысловую
    проверку соответствия шагу (Задача 1). Сцена, помеченная needs_review
    (валидация исчерпала ретраи), сгенерирована, но шаг не закрывает —
    иначе шаг «съедается» одной валидной сценой, а расхождение проходит молча.
    """
    required = max(roadmap.scenes_count, 1)
    valid = sum(
        1 for scene in scenes
        if scene.roadmap_id == roadmap.id and not scene.needs_review
    )
    return valid >= required


def resolve_next_slot(
    roadmaps: list[Roadmap], scenes: list[Scene]
) -> NextSceneSlot | None:
    """Следующий слот генерации или None, если роадмап пройден.

    Слот выбирается по закрытости шага (is_step_closed), а не по счёту сцен:
    незакрытый шаг остаётся следующим, пока не наберёт все свои валидные сцены.

    Чистая функция: используется и NovelState (генерация), и NovelPlaybackService
    (определение статуса воспроизведения), поэтому не привязана к NovelState.
    """
    for roadmap in roadmaps:
        if not is_step_closed(roadmap, scenes):
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
        # Сцены, не прошедшие смысловую проверку (needs_review), не показываются и
        # не должны попадать в контекст следующих генераций.
        playable = [s for s in self._scenes if not s.needs_review]
        return playable[-PREVIOUS_SCENES_LIMIT:]

    def scene_at(self, order: int) -> Scene | None:
        return next((s for s in self._scenes if s.order == order), None)

    def resolve_next_slot(self) -> NextSceneSlot | None:
        """Делегат в свободную функцию — чтобы вызывающему не тащить два списка."""
        return resolve_next_slot(self._roadmaps, self._scenes)

    def is_step_closed(self, roadmap: Roadmap) -> bool:
        """Закрыт ли шаг роадмапа в этом снапшоте (все сцены сгенерированы и валидны)."""
        return is_step_closed(roadmap, self._scenes)

    @property
    def last_story_context(self) -> str | None:
        for scene in reversed(self._scenes):
            if scene.story_context:
                return scene.story_context
        return None

    @property
    def previous_dialogue_lines(self) -> list[DialogueLine]:
        return self._dialogue_lines[-PREVIOUS_LINES_LIMIT:]
