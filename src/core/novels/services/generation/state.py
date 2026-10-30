from dataclasses import dataclass

from src.core.novels.models import (
    DialogueLine,
    PlayerChoice,
    Roadmap,
    RoadmapChoice,
    Scene,
)

PREVIOUS_SCENES_LIMIT = 5
PREVIOUS_LINES_LIMIT = 4


@dataclass(frozen=True, slots=True)
class NextSceneSlot:
    """Куда попадёт следующая сцена: шаг роадмапа + позиция внутри шага.

    ``order`` — глобальный сквозной номер сцены (для ``scenes.order`` и упорядочивания
    сыгранного пути); ``position`` — номер сцены внутри шага роадмапа (1..scenes_count),
    он же ключ идемпотентности вместе с ``roadmap.id``.
    """

    roadmap: Roadmap
    position: int
    order: int


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


def next_scene_position(roadmap_id: int, scenes: list[Scene]) -> int:
    """Номер следующей сцены внутри шага (валидные сцены считаются по порядку)."""
    valid = sum(
        1 for s in scenes
        if s.roadmap_id == roadmap_id and not s.needs_review
    )
    return valid + 1


def _resolve_root(roadmaps: list[Roadmap]) -> Roadmap | None:
    """Корень дерева: шаг без родителя. Fallback — первый по (branch_id, depth)."""
    root = next((r for r in roadmaps if r.parent_roadmap_id is None), None)
    if root is not None:
        return root
    if roadmaps:
        return min(roadmaps, key=lambda r: (r.branch_id, r.depth))
    return None


def _chosen_next(
    choices: list[RoadmapChoice], player_choices: list[PlayerChoice]
) -> dict[int, int]:
    """Сопоставление «шаг выбора -> следующий шаг» по журналу игрока.

    Для форка, который ещё не сгенерирован (next_roadmap_id is None), записи не
    будет — это означает, что путь ещё ждёт генерации ветки.
    """
    choice_by_id = {c.id: c for c in choices}
    chosen: dict[int, int] = {}
    for pc in player_choices:
        choice = choice_by_id.get(pc.roadmap_choice_id)
        if choice is None or choice.next_roadmap_id is None:
            continue
        chosen[choice.roadmap_id] = choice.next_roadmap_id
    return chosen


def resolve_next_slot(
    roadmaps: list[Roadmap],
    scenes: list[Scene],
    choices: list[RoadmapChoice],
    player_choices: list[PlayerChoice],
) -> NextSceneSlot | None:
    """Следующий слот генерации или None, если новелла пройдена / ждёт выбора.

    Идёт по дереву роадмапа от корня: закрытые шаги пропускаются; на шаге с выбором
    следующий шаг берётся из журнала игрока (выбранный вариант), на линейном — из
    единственного ребёнка. Возвращает первый незакрытый шаг как слот.

    Чистая функция: используется и NovelState (генерация), и NovelPlaybackService
    (статус воспроизведения), поэтому не привязана к NovelState.
    """
    by_id = {r.id: r for r in roadmaps}
    children: dict[int, list[Roadmap]] = {}
    for r in roadmaps:
        if r.parent_roadmap_id is not None:
            children.setdefault(r.parent_roadmap_id, []).append(r)

    chosen_next = _chosen_next(choices, player_choices)
    current = _resolve_root(roadmaps)
    while current is not None:
        if not is_step_closed(current, scenes):
            return NextSceneSlot(
                roadmap=current,
                position=next_scene_position(current.id, scenes),
                order=len(scenes) + 1,
            )
        if current.target_choice:
            next_id = chosen_next.get(current.id)
            if next_id is None:
                # Игрок на развилке, но выбор не зафиксирован (или ветка ещё не
                # сгенерирована) — это не слот генерации, а ожидание выбора.
                return None
            current = by_id.get(next_id)
        else:
            kids = children.get(current.id) or []
            current = kids[0] if kids else None
    return None


class NovelState:
    """Иммутабельный снапшот roadmaps/scenes/lines/choices на момент чтения.

    Используется SceneContinuationService: помимо следующего слота, даёт
    контекст для LLM (last_scenes, last_story_context, previous_dialogue_lines).
    """

    __slots__ = (
        "_choices",
        "_dialogue_lines",
        "_player_choices",
        "_roadmaps",
        "_scenes",
    )

    def __init__(
        self,
        roadmaps: list[Roadmap],
        scenes: list[Scene],
        dialogue_lines: list[DialogueLine],
        choices: list[RoadmapChoice],
        player_choices: list[PlayerChoice],
    ) -> None:
        self._roadmaps = roadmaps
        self._scenes = sorted(scenes, key=lambda s: s.order)
        self._dialogue_lines = dialogue_lines
        self._choices = choices
        self._player_choices = player_choices

    @property
    def scenes(self) -> list[Scene]:
        return self._scenes

    @property
    def roadmaps(self) -> list[Roadmap]:
        return self._roadmaps

    @property
    def choices(self) -> list[RoadmapChoice]:
        return self._choices

    @property
    def player_choices(self) -> list[PlayerChoice]:
        return self._player_choices

    @property
    def last_scenes(self) -> list[Scene]:
        # Сцены, не прошедшие смысловую проверку (needs_review), не показываются и
        # не должны попадать в контекст следующих генераций.
        playable = [s for s in self._scenes if not s.needs_review]
        return playable[-PREVIOUS_SCENES_LIMIT:]

    def scene_at(self, order: int) -> Scene | None:
        return next((s for s in self._scenes if s.order == order), None)

    def scene_at_step_position(self, roadmap_id: int, position: int) -> Scene | None:
        """Сцена с номером position внутри шага (среди валидных), или None."""
        step_scenes = [
            s for s in self._scenes
            if s.roadmap_id == roadmap_id and not s.needs_review
        ]
        step_scenes.sort(key=lambda s: s.order)
        if 1 <= position <= len(step_scenes):
            return step_scenes[position - 1]
        return None

    def resolve_next_slot(self) -> NextSceneSlot | None:
        """Делегат в свободную функцию — чтобы вызывающему не тащить все списки."""
        return resolve_next_slot(
            self._roadmaps, self._scenes, self._choices, self._player_choices
        )

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

    @property
    def dialogue_lines(self) -> list[DialogueLine]:
        return self._dialogue_lines
