from src.core.novels.models import PlayerChoice, RoadmapChoice
from src.core.novels.services.generation.state import (
    PREVIOUS_LINES_LIMIT,
    PREVIOUS_SCENES_LIMIT,
    NovelState,
    is_step_closed,
    resolve_incomplete_scene_slot,
    resolve_next_slot,
    scene_ids_with_lines,
)
from tests.factories import dialogue_line_domain, roadmap_domain, scene_domain


def _choice(
    choice_id: int,
    roadmap_id: int,
    next_roadmap_id: int | None,
) -> RoadmapChoice:
    return RoadmapChoice(
        id=choice_id,
        created_at=None,
        updated_at=None,
        roadmap_id=roadmap_id,
        order=1,
        text="Да",
        is_true=True,
        next_roadmap_id=next_roadmap_id,
    )


def _player_choice(choice_id: int, *, novel_id: int = 1) -> PlayerChoice:
    return PlayerChoice(
        id=choice_id,
        created_at=None,
        updated_at=None,
        novel_id=novel_id,
        roadmap_choice_id=choice_id,
    )


# ---------------------------------------------------------------------------
# resolve_next_slot — чистая функция выбора следующего слота генерации
# ---------------------------------------------------------------------------


class TestResolveNextSlot:
    def test_returns_first_incomplete_roadmap(self):
        roadmaps = [
            roadmap_domain(id=10, depth=1, scenes_count=2),
            roadmap_domain(id=20, depth=2, parent_roadmap_id=10, scenes_count=1),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]

        slot = resolve_next_slot(roadmaps, scenes, [], [])

        assert slot is not None
        assert slot.roadmap.id == 10
        assert slot.position == 2
        assert slot.order == 2

    def test_skips_completed_roadmap_to_the_next_one(self):
        roadmaps = [
            roadmap_domain(id=10, depth=1, scenes_count=1),
            roadmap_domain(id=20, depth=2, parent_roadmap_id=10, scenes_count=2),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]

        slot = resolve_next_slot(roadmaps, scenes, [], [])

        assert slot is not None
        assert slot.roadmap.id == 20
        assert slot.position == 1
        assert slot.order == 2

    def test_returns_none_when_all_roadmaps_complete(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=1)]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]

        assert resolve_next_slot(roadmaps, scenes, [], []) is None

    def test_returns_none_for_empty_roadmaps(self):
        assert resolve_next_slot([], [], [], []) is None

    def test_scenes_count_zero_is_treated_as_one(self):
        """Шаг с scenes_count=0 всё равно требует хотя бы одну сцену."""
        roadmaps = [roadmap_domain(id=10, scenes_count=0)]

        assert resolve_next_slot(roadmaps, [], [], []) is not None
        assert (
            resolve_next_slot(
                roadmaps, [scene_domain(roadmap_id=10, order=1)], [], []
            )
            is None
        )

    def test_order_equals_total_scene_count_plus_one(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=5)]
        scenes = [scene_domain(roadmap_id=10, order=i) for i in (1, 2, 3)]

        slot = resolve_next_slot(roadmaps, scenes, [], [])

        assert slot is not None
        assert slot.order == 4

    def test_scenes_of_other_roadmaps_not_counted_toward_step(self):
        """Сцены другого шага не закрывают scenes_count текущего шага."""
        roadmaps = [roadmap_domain(id=10, scenes_count=2)]
        scenes = [scene_domain(id=1, roadmap_id=99, order=1)]

        slot = resolve_next_slot(roadmaps, scenes, [], [])

        assert slot is not None
        assert slot.roadmap.id == 10
        assert slot.position == 1

    def test_needs_review_scene_does_not_close_step(self):
        """Сцена, не прошедшая валидацию (needs_review), не закрывает шаг."""
        roadmaps = [roadmap_domain(id=10, scenes_count=2)]
        scenes = [
            scene_domain(id=1, roadmap_id=10, order=1),
            scene_domain(id=2, roadmap_id=10, order=2, needs_review=True),
        ]

        slot = resolve_next_slot(roadmaps, scenes, [], [])

        # Одна валидная сцена из двух — шаг не закрыт, следующая сцена этого шага.
        assert slot is not None
        assert slot.roadmap.id == 10
        assert slot.position == 2
        assert slot.order == 3

    def test_linear_path_goes_to_the_only_child(self):
        roadmaps = [
            roadmap_domain(id=10, depth=1, scenes_count=1),
            roadmap_domain(id=20, depth=2, parent_roadmap_id=10, scenes_count=1),
            roadmap_domain(id=30, depth=3, parent_roadmap_id=20, scenes_count=1),
        ]
        scenes = [
            scene_domain(id=1, roadmap_id=10, order=1),
            scene_domain(id=2, roadmap_id=20, order=2),
        ]

        slot = resolve_next_slot(roadmaps, scenes, [], [])

        assert slot is not None
        assert slot.roadmap.id == 30
        assert slot.order == 3

    def test_choice_path_follows_player_journal(self):
        roadmaps = [
            roadmap_domain(id=10, depth=1, target_choice=True, scenes_count=1),
            roadmap_domain(id=20, depth=2, parent_roadmap_id=10, scenes_count=1),
            roadmap_domain(id=30, depth=2, parent_roadmap_id=10, scenes_count=1),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]
        choices = [_choice(500, 10, next_roadmap_id=30)]

        slot = resolve_next_slot(
            roadmaps, scenes, choices, [_player_choice(500)]
        )

        assert slot is not None
        assert slot.roadmap.id == 30

    def test_choice_without_player_choice_is_not_a_slot(self):
        """Развилка без зафиксированного выбора — ожидание выбора, не генерация."""
        roadmaps = [
            roadmap_domain(id=10, depth=1, target_choice=True, scenes_count=1),
            roadmap_domain(id=20, depth=2, parent_roadmap_id=10, scenes_count=1),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]
        choices = [_choice(500, 10, next_roadmap_id=20)]

        assert resolve_next_slot(roadmaps, scenes, choices, []) is None

    def test_choice_into_not_yet_generated_branch_is_not_a_slot(self):
        roadmaps = [
            roadmap_domain(id=10, depth=1, target_choice=True, scenes_count=1),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]
        choices = [_choice(500, 10, next_roadmap_id=None)]

        assert (
            resolve_next_slot(roadmaps, scenes, choices, [_player_choice(500)])
            is None
        )


# ---------------------------------------------------------------------------
# resolve_incomplete_scene_slot — сцена записана, но реплик ещё нет
# ---------------------------------------------------------------------------


class TestResolveIncompleteSceneSlot:
    def test_returns_scene_without_lines(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=1)]
        scenes = [scene_domain(id=100, roadmap_id=10, order=1)]

        slot = resolve_incomplete_scene_slot(
            roadmaps, scenes, [], [], ready_scene_ids=set()
        )

        assert slot is not None
        assert slot.roadmap.id == 10
        assert slot.position == 1
        assert slot.order == 1

    def test_skips_scenes_with_lines(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=2)]
        scenes = [
            scene_domain(id=100, roadmap_id=10, order=1),
            scene_domain(id=101, roadmap_id=10, order=2),
        ]

        slot = resolve_incomplete_scene_slot(
            roadmaps, scenes, [], [], ready_scene_ids={100}
        )

        assert slot is not None
        assert slot.position == 2
        assert slot.order == 2

    def test_returns_none_when_every_scene_has_lines(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=1)]
        scenes = [scene_domain(id=100, roadmap_id=10, order=1)]

        assert (
            resolve_incomplete_scene_slot(
                roadmaps, scenes, [], [], ready_scene_ids={100}
            )
            is None
        )

    def test_needs_review_scene_is_not_a_slot(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=1)]
        scenes = [
            scene_domain(
                id=100, roadmap_id=10, order=1, needs_review=True
            )
        ]

        assert (
            resolve_incomplete_scene_slot(
                roadmaps, scenes, [], [], ready_scene_ids=set()
            )
            is None
        )

    def test_earlier_step_wins_over_later_step(self):
        roadmaps = [
            roadmap_domain(id=10, depth=1, scenes_count=2),
            roadmap_domain(id=20, depth=2, parent_roadmap_id=10, scenes_count=1),
        ]
        scenes = [
            scene_domain(id=100, roadmap_id=10, order=1),
            scene_domain(id=101, roadmap_id=10, order=2),
            scene_domain(id=200, roadmap_id=20, order=3),
        ]

        slot = resolve_incomplete_scene_slot(
            roadmaps, scenes, [], [], ready_scene_ids={100}
        )

        assert slot is not None
        assert slot.roadmap.id == 10
        assert slot.position == 2

    def test_same_order_ties_are_broken_by_id(self):
        """Сортировка шага та же, что у генерации: (order, id)."""
        roadmaps = [roadmap_domain(id=10, scenes_count=2)]
        scenes = [
            scene_domain(id=20, roadmap_id=10, order=1),
            scene_domain(id=10, roadmap_id=10, order=1),
        ]

        slot = resolve_incomplete_scene_slot(
            roadmaps, scenes, [], [], ready_scene_ids={10}
        )

        assert slot is not None
        assert slot.order == 1
        assert slot.position == 2


# ---------------------------------------------------------------------------
# scene_ids_with_lines
# ---------------------------------------------------------------------------


class TestSceneIdsWithLines:
    def test_collects_unique_scene_ids(self):
        lines = [
            dialogue_line_domain(id=1, scene_id=100),
            dialogue_line_domain(id=2, scene_id=100),
            dialogue_line_domain(id=3, scene_id=200),
        ]

        assert scene_ids_with_lines(lines) == {100, 200}

    def test_empty_lines(self):
        assert scene_ids_with_lines([]) == set()


# ---------------------------------------------------------------------------
# is_step_closed — явный признак закрытия шага
# ---------------------------------------------------------------------------


class TestIsStepClosed:
    def test_closed_when_valid_scenes_reach_scenes_count(self):
        roadmap = roadmap_domain(id=10, scenes_count=2)
        scenes = [
            scene_domain(roadmap_id=10, order=1),
            scene_domain(roadmap_id=10, order=2),
        ]

        assert is_step_closed(roadmap, scenes) is True

    def test_not_closed_with_one_scene_for_two_scene_step(self):
        """Шаг из 2 сцен не может быть закрыт одной сценой."""
        roadmap = roadmap_domain(id=10, scenes_count=2)
        scenes = [scene_domain(roadmap_id=10, order=1)]

        assert is_step_closed(roadmap, scenes) is False

    def test_needs_review_scene_does_not_close_step(self):
        roadmap = roadmap_domain(id=10, scenes_count=2)
        scenes = [
            scene_domain(roadmap_id=10, order=1),
            scene_domain(roadmap_id=10, order=2, needs_review=True),
        ]

        assert is_step_closed(roadmap, scenes) is False

    def test_scenes_count_zero_treated_as_one(self):
        roadmap = roadmap_domain(id=10, scenes_count=0)

        assert is_step_closed(roadmap, []) is False
        assert is_step_closed(roadmap, [scene_domain(roadmap_id=10)]) is True

    def test_scenes_of_other_roadmaps_ignored(self):
        roadmap = roadmap_domain(id=10, scenes_count=1)
        scenes = [scene_domain(roadmap_id=99, order=1)]

        assert is_step_closed(roadmap, scenes) is False


# ---------------------------------------------------------------------------
# NovelState — снапшот состояния новеллы
# ---------------------------------------------------------------------------


class TestNovelState:
    def test_scenes_sorted_by_order(self):
        scenes = [
            scene_domain(id=3, order=3),
            scene_domain(id=1, order=1),
            scene_domain(id=2, order=2),
        ]

        state = NovelState([], scenes, [], [], [])

        assert [s.order for s in state.scenes] == [1, 2, 3]

    def test_last_scenes_limited_to_five(self):
        scenes = [scene_domain(id=i, order=i) for i in range(1, 8)]

        state = NovelState([], scenes, [], [], [])

        assert len(state.last_scenes) == PREVIOUS_SCENES_LIMIT
        assert [s.order for s in state.last_scenes] == [3, 4, 5, 6, 7]

    def test_last_scenes_excludes_needs_review(self):
        """Сцены с needs_review не попадают в контекст следующих генераций."""
        scenes = [
            scene_domain(id=1, order=1),
            scene_domain(id=2, order=2, needs_review=True),
            scene_domain(id=3, order=3),
        ]

        state = NovelState([], scenes, [], [], [])

        assert [s.id for s in state.last_scenes] == [1, 3]

    def test_last_scenes_before_excludes_future_scenes(self):
        """Контекст сцены не должен содержать сцены из будущего."""
        scenes = [
            scene_domain(id=1, order=1),
            scene_domain(id=2, order=2),
            scene_domain(id=3, order=3),
        ]

        state = NovelState([], scenes, [], [], [])

        assert [s.id for s in state.last_scenes_before(2)] == [1]
        assert [s.id for s in state.last_scenes_before(3)] == [1, 2]

    def test_last_scenes_before_excludes_needs_review(self):
        scenes = [
            scene_domain(id=1, order=1),
            scene_domain(id=2, order=2, needs_review=True),
        ]

        state = NovelState([], scenes, [], [], [])

        assert [s.id for s in state.last_scenes_before(3)] == [1]

    def test_scene_at_returns_scene_by_order(self):
        scenes = [scene_domain(id=1, order=2), scene_domain(id=2, order=1)]

        state = NovelState([], scenes, [], [], [])

        assert state.scene_at(1).id == 2
        assert state.scene_at(2).id == 1

    def test_scene_at_returns_none_for_missing_order(self):
        state = NovelState([], [scene_domain(id=1, order=1)], [], [], [])

        assert state.scene_at(99) is None

    def test_scene_at_step_position_uses_same_sort_as_playback(self):
        """Позиция в шаге считается по (order, id), как и в хвосте проигрывания."""
        scenes = [
            scene_domain(id=20, roadmap_id=10, order=1),
            scene_domain(id=10, roadmap_id=10, order=1),
            scene_domain(id=30, roadmap_id=10, order=2),
        ]

        state = NovelState([], scenes, [], [], [])

        assert state.scene_at_step_position(10, 1).id == 10
        assert state.scene_at_step_position(10, 2).id == 20
        assert state.scene_at_step_position(10, 3).id == 30

    def test_scene_at_step_position_skips_needs_review(self):
        scenes = [
            scene_domain(id=1, roadmap_id=10, order=1, needs_review=True),
            scene_domain(id=2, roadmap_id=10, order=2),
        ]

        state = NovelState([], scenes, [], [], [])

        assert state.scene_at_step_position(10, 1).id == 2
        assert state.scene_at_step_position(10, 2) is None

    def test_last_story_context_returns_last_non_empty(self):
        scenes = [
            scene_domain(id=1, order=1, story_context="контекст 1"),
            scene_domain(id=2, order=2, story_context=None),
            scene_domain(id=3, order=3, story_context="контекст 3"),
        ]

        state = NovelState([], scenes, [], [], [])

        assert state.last_story_context == "контекст 3"

    def test_last_story_context_none_when_all_empty(self):
        scenes = [
            scene_domain(id=1, order=1, story_context=None),
            scene_domain(id=2, order=2, story_context=None),
        ]

        state = NovelState([], scenes, [], [], [])

        assert state.last_story_context is None

    def test_last_story_context_before_excludes_future(self):
        scenes = [
            scene_domain(id=1, order=1, story_context="прошлое"),
            scene_domain(id=2, order=2, story_context="будущее"),
        ]

        state = NovelState([], scenes, [], [], [])

        assert state.last_story_context_before(2) == "прошлое"
        assert state.last_story_context_before(1) is None

    def test_previous_dialogue_lines_limited_to_four(self):
        lines = [dialogue_line_domain(id=i, order=i) for i in range(1, 7)]

        state = NovelState([], [], lines, [], [])

        assert len(state.previous_dialogue_lines) == PREVIOUS_LINES_LIMIT
        assert [l.order for l in state.previous_dialogue_lines] == [3, 4, 5, 6]

    def test_previous_dialogue_lines_keeps_input_order(self):
        """previous_dialogue_lines не сортирует — просто берёт хвост списка."""
        lines = [
            dialogue_line_domain(id=2, order=2),
            dialogue_line_domain(id=1, order=1),
        ]

        state = NovelState([], [], lines, [], [])

        assert [l.id for l in state.previous_dialogue_lines] == [2, 1]

    def test_previous_dialogue_lines_before_excludes_future_scenes(self):
        scenes = [
            scene_domain(id=1, order=1),
            scene_domain(id=2, order=2),
        ]
        lines = [
            dialogue_line_domain(id=10, scene_id=1, order=1),
            dialogue_line_domain(id=20, scene_id=2, order=2),
        ]

        state = NovelState([], scenes, lines, [], [])

        assert [l.id for l in state.previous_dialogue_lines_before(2)] == [10]
        assert [l.id for l in state.previous_dialogue_lines_before(3)] == [10, 20]

    def test_scene_has_lines(self):
        scenes = [scene_domain(id=1, order=1), scene_domain(id=2, order=2)]
        lines = [dialogue_line_domain(scene_id=1)]

        state = NovelState([], scenes, lines, [], [])

        assert state.scene_has_lines(1) is True
        assert state.scene_has_lines(2) is False
        assert state.scene_has_lines(None) is False

    def test_first_scene_without_lines_before_returns_earlier_orphan(self):
        """Шаг «закрыт» по числу сцен, но первая сцена ещё без реплик."""
        roadmaps = [
            roadmap_domain(id=10, depth=1, scenes_count=1),
            roadmap_domain(id=20, depth=2, parent_roadmap_id=10, scenes_count=1),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]

        state = NovelState(roadmaps, scenes, [], [], [])

        assert state.first_scene_without_lines_before(2).id == 1

    def test_first_scene_without_lines_before_none_when_all_written(self):
        roadmaps = [
            roadmap_domain(id=10, depth=1, scenes_count=1),
            roadmap_domain(id=20, depth=2, parent_roadmap_id=10, scenes_count=1),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]
        lines = [dialogue_line_domain(scene_id=1)]

        state = NovelState(roadmaps, scenes, lines, [], [])

        assert state.first_scene_without_lines_before(2) is None

    def test_first_scene_without_lines_before_ignores_needs_review(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=1)]
        scenes = [
            scene_domain(
                id=1, roadmap_id=10, order=1, needs_review=True
            )
        ]

        state = NovelState(roadmaps, scenes, [], [], [])

        assert state.first_scene_without_lines_before(2) is None

    def test_first_scene_without_lines_before_ignores_unselected_branch(self):
        """Сцена невыбранной ветки не блокирует генерацию выбранной."""
        roadmaps = [
            roadmap_domain(id=10, depth=1, target_choice=True, scenes_count=1),
            roadmap_domain(id=20, depth=2, parent_roadmap_id=10, scenes_count=1),
            roadmap_domain(id=30, depth=2, parent_roadmap_id=10, scenes_count=1),
        ]
        scenes = [
            scene_domain(id=1, roadmap_id=10, order=1),
            scene_domain(id=300, roadmap_id=30, order=2),  # невыбранная ветка
        ]
        lines = [dialogue_line_domain(scene_id=1)]
        choices = [_choice(500, 10, next_roadmap_id=20)]

        state = NovelState(
            roadmaps, scenes, lines, choices, [_player_choice(500)]
        )

        assert state.first_scene_without_lines_before(2) is None

    def test_resolve_next_slot_delegates_to_free_function(self):
        roadmaps = [
            roadmap_domain(id=10, depth=1, scenes_count=2),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]

        state = NovelState(roadmaps, scenes, [], [], [])
        slot = state.resolve_next_slot()

        assert slot is not None
        assert slot.roadmap.id == 10
        assert slot.position == 2
        assert slot.order == 2
