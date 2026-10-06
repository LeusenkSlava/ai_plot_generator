from src.core.novels.services.state import (
    PREVIOUS_LINES_LIMIT,
    PREVIOUS_SCENES_LIMIT,
    NovelState,
    resolve_next_slot,
)
from tests.factories import dialogue_line_domain, roadmap_domain, scene_domain

# ---------------------------------------------------------------------------
# resolve_next_slot — чистая функция выбора следующего слота генерации
# ---------------------------------------------------------------------------


class TestResolveNextSlot:
    def test_returns_first_incomplete_roadmap(self):
        roadmaps = [
            roadmap_domain(id=10, step_id=1, scenes_count=2),
            roadmap_domain(id=20, step_id=2, scenes_count=1),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]

        slot = resolve_next_slot(roadmaps, scenes)

        assert slot is not None
        assert slot.roadmap.id == 10
        assert slot.order == 2

    def test_skips_completed_roadmap_to_the_next_one(self):
        roadmaps = [
            roadmap_domain(id=10, step_id=1, scenes_count=1),
            roadmap_domain(id=20, step_id=2, scenes_count=2),
        ]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]

        slot = resolve_next_slot(roadmaps, scenes)

        assert slot is not None
        assert slot.roadmap.id == 20
        assert slot.order == 2

    def test_returns_none_when_all_roadmaps_complete(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=1)]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]

        assert resolve_next_slot(roadmaps, scenes) is None

    def test_returns_none_for_empty_roadmaps(self):
        assert resolve_next_slot([], []) is None

    def test_scenes_count_zero_is_treated_as_one(self):
        """Шаг с scenes_count=0 всё равно требует хотя бы одну сцену."""
        roadmaps = [roadmap_domain(id=10, scenes_count=0)]

        assert resolve_next_slot(roadmaps, []) is not None
        assert (
            resolve_next_slot(roadmaps, [scene_domain(roadmap_id=10, order=1)]) is None
        )

    def test_order_equals_total_scene_count_plus_one(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=5)]
        scenes = [scene_domain(roadmap_id=10, order=i) for i in (1, 2, 3)]

        slot = resolve_next_slot(roadmaps, scenes)

        assert slot.order == 4

    def test_scenes_of_other_roadmaps_not_counted_toward_step(self):
        """Сцены другого шага не закрывают scenes_count текущего шага."""
        roadmaps = [roadmap_domain(id=10, scenes_count=2)]
        scenes = [scene_domain(id=1, roadmap_id=99, order=1)]

        slot = resolve_next_slot(roadmaps, scenes)

        assert slot is not None
        assert slot.roadmap.id == 10


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

        state = NovelState([], scenes, [])

        assert [s.order for s in state.scenes] == [1, 2, 3]

    def test_last_scenes_limited_to_five(self):
        scenes = [scene_domain(id=i, order=i) for i in range(1, 8)]

        state = NovelState([], scenes, [])

        assert len(state.last_scenes) == PREVIOUS_SCENES_LIMIT
        assert [s.order for s in state.last_scenes] == [3, 4, 5, 6, 7]

    def test_scene_at_returns_scene_by_order(self):
        scenes = [scene_domain(id=1, order=2), scene_domain(id=2, order=1)]

        state = NovelState([], scenes, [])

        assert state.scene_at(1).id == 2
        assert state.scene_at(2).id == 1

    def test_scene_at_returns_none_for_missing_order(self):
        state = NovelState([], [scene_domain(id=1, order=1)], [])

        assert state.scene_at(99) is None

    def test_last_story_context_returns_last_non_empty(self):
        scenes = [
            scene_domain(id=1, order=1, story_context="контекст 1"),
            scene_domain(id=2, order=2, story_context=None),
            scene_domain(id=3, order=3, story_context="контекст 3"),
        ]

        state = NovelState([], scenes, [])

        assert state.last_story_context == "контекст 3"

    def test_last_story_context_none_when_all_empty(self):
        scenes = [
            scene_domain(id=1, order=1, story_context=None),
            scene_domain(id=2, order=2, story_context=None),
        ]

        state = NovelState([], scenes, [])

        assert state.last_story_context is None

    def test_previous_dialogue_lines_limited_to_four(self):
        lines = [dialogue_line_domain(id=i, order=i) for i in range(1, 7)]

        state = NovelState([], [], lines)

        assert len(state.previous_dialogue_lines) == PREVIOUS_LINES_LIMIT
        assert [l.order for l in state.previous_dialogue_lines] == [3, 4, 5, 6]

    def test_previous_dialogue_lines_keeps_input_order(self):
        """previous_dialogue_lines не сортирует — просто берёт хвост списка."""
        lines = [
            dialogue_line_domain(id=2, order=2),
            dialogue_line_domain(id=1, order=1),
        ]

        state = NovelState([], [], lines)

        assert [l.id for l in state.previous_dialogue_lines] == [2, 1]

    def test_resolve_next_slot_delegates_to_free_function(self):
        roadmaps = [roadmap_domain(id=10, scenes_count=2)]
        scenes = [scene_domain(id=1, roadmap_id=10, order=1)]

        state = NovelState(roadmaps, scenes, [])
        slot = state.resolve_next_slot()

        assert slot is not None
        assert slot.roadmap.id == 10
        assert slot.order == 2
