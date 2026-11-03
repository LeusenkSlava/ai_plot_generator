from collections.abc import Iterator
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


def scene_ids_with_lines(lines: list[DialogueLine]) -> set[int]:
    """id сцен, у которых есть реплики."""
    return {line.scene_id for line in lines}


def _valid_step_scenes(roadmap_id: int, scenes: list[Scene]) -> list[Scene]:
    """Валидные (не needs_review) сцены шага в порядке проигрывания.

    Единая сортировка ``(order, id)``: без неё две ветки обхода выбирали бы
    разные сцены при одинаковом ``order`` (например, старые данные с дублем).
    """
    return sorted(
        (s for s in scenes if s.roadmap_id == roadmap_id and not s.needs_review),
        key=lambda s: (s.order, s.id or 0),
    )


def _iter_path_steps(
    roadmaps: list[Roadmap],
    scenes: list[Scene],
    choices: list[RoadmapChoice],
    player_choices: list[PlayerChoice],
) -> Iterator[tuple[Roadmap, list[Scene]]]:
    """Шаги сыгранного пути от корня: (шаг, его валидные сцены).

    Путь идёт по журналу игрока на развилках и по единственному ребёнку на
    линейных шагах. Останавливается, когда шаг с выбором ещё не выбран: ветка
    без зафиксированного выбора не является частью пути.
    """
    by_id = {r.id: r for r in roadmaps}
    children: dict[int, list[Roadmap]] = {}
    for roadmap in roadmaps:
        if roadmap.parent_roadmap_id is not None:
            children.setdefault(roadmap.parent_roadmap_id, []).append(roadmap)

    chosen_next = _chosen_next(choices, player_choices)
    current = _resolve_root(roadmaps)
    while current is not None:
        yield current, _valid_step_scenes(current.id, scenes)
        if current.target_choice:
            next_id = chosen_next.get(current.id)
            if next_id is None:
                return
            current = by_id.get(next_id)
        else:
            kids = children.get(current.id) or []
            current = kids[0] if kids else None


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
    for roadmap, _ in _iter_path_steps(roadmaps, scenes, choices, player_choices):
        if not is_step_closed(roadmap, scenes):
            return NextSceneSlot(
                roadmap=roadmap,
                position=next_scene_position(roadmap.id, scenes),
                order=len(scenes) + 1,
            )
    return None


def resolve_incomplete_scene_slot(
    roadmaps: list[Roadmap],
    scenes: list[Scene],
    choices: list[RoadmapChoice],
    player_choices: list[PlayerChoice],
    ready_scene_ids: set[int],
) -> NextSceneSlot | None:
    """Слот первой сцены сыгранного пути, у которой ещё нет реплик.

    ``resolve_next_slot`` считает шаг закрытым по числу валидных сцен, а сцена
    коммитится до генерации диалога. Без этой проверки проигрывание отдаёт
    ``finished`` за сцену до развилки. ``position`` — место сцены среди валидных
    сцен шага: повторная задача должна дописать эту сцену, а не создать дубль.
    """
    for roadmap, step_scenes in _iter_path_steps(
        roadmaps, scenes, choices, player_choices
    ):
        for position, scene in enumerate(step_scenes, start=1):
            if scene.id is not None and scene.id not in ready_scene_ids:
                return NextSceneSlot(
                    roadmap=roadmap,
                    position=position,
                    order=scene.order,
                )
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
        "_ready_scene_ids",
        "_roadmaps",
        "_scene_order_by_id",
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
        self._ready_scene_ids = scene_ids_with_lines(dialogue_lines)
        self._scene_order_by_id = {
            scene.id: scene.order for scene in self._scenes if scene.id is not None
        }

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

    def last_scenes_before(self, order: int) -> list[Scene]:
        """Последние сцены строго до ``order`` — контекст конкретной сцены.

        Нужен для «сироты» (сцена записана, реплик нет): глобальный хвост
        снапшота может содержать сцены из будущего, если сцену когда-то обогнали.
        """
        playable = [
            s for s in self._scenes if not s.needs_review and s.order < order
        ]
        return playable[-PREVIOUS_SCENES_LIMIT:]

    def scene_at(self, order: int) -> Scene | None:
        return next((s for s in self._scenes if s.order == order), None)

    def scene_at_step_position(self, roadmap_id: int, position: int) -> Scene | None:
        """Сцена с номером position внутри шага (среди валидных), или None."""
        step_scenes = _valid_step_scenes(roadmap_id, self._scenes)
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

    def scene_has_lines(self, scene_id: int | None) -> bool:
        """Есть ли у сцены реплики (сцена без реплик ещё не готова к проигрыванию)."""
        if scene_id is None:
            return False
        return scene_id in self._ready_scene_ids

    def first_scene_without_lines_before(self, order: int) -> Scene | None:
        """Более ранняя сцена пути, у которой ещё нет реплик.

        Сцена коммитится до генерации диалога, поэтому повторная доставка может
        застать шаг уже «закрытым» по числу сцен. Генерировать следующий слот
        поверх недописанной сцены нельзя: диалог потеряет её контекст, а
        компенсация следующей сцены каскадом удалит её реплики.
        """
        for _roadmap, step_scenes in _iter_path_steps(
            self._roadmaps, self._scenes, self._choices, self._player_choices
        ):
            for scene in step_scenes:
                if scene.order >= order:
                    return None
                if not self.scene_has_lines(scene.id):
                    return scene
        return None

    @property
    def last_story_context(self) -> str | None:
        for scene in reversed(self._scenes):
            if scene.story_context:
                return scene.story_context
        return None

    def last_story_context_before(self, order: int) -> str | None:
        """Последнее изложение строго до ``order`` (без фактов из будущего)."""
        for scene in reversed(self._scenes):
            if scene.order < order and scene.story_context:
                return scene.story_context
        return None

    @property
    def previous_dialogue_lines(self) -> list[DialogueLine]:
        return self._dialogue_lines[-PREVIOUS_LINES_LIMIT:]

    def dialogue_lines_before(self, order: int) -> list[DialogueLine]:
        """Реплики сцен строго до ``order`` — контекст конкретной сцены."""
        return [
            line
            for line in self._dialogue_lines
            if self._scene_order_by_id.get(line.scene_id, 0) < order
        ]

    def previous_dialogue_lines_before(self, order: int) -> list[DialogueLine]:
        """Последние реплики до ``order`` (хвост ``dialogue_lines_before``)."""
        return self.dialogue_lines_before(order)[-PREVIOUS_LINES_LIMIT:]

    @property
    def dialogue_lines(self) -> list[DialogueLine]:
        return self._dialogue_lines
