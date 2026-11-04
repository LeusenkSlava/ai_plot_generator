from src.core.novels.exceptions import GenerationError
from src.core.novels.models import PlotDesign, PlotThread
from src.core.novels.services.generation.generators.plot_design import parse_design
from src.core.novels.services.generation.prompts.shapes import (
    DEFAULT_SHAPE,
    STORY_SHAPES,
    render_shape_block,
    render_shape_catalog,
)

CAST = {"Совёнок", "Алиса", "Ольга"}


def _payload(**overrides) -> dict:
    payload = {
        "shape": "relationship_arc",
        "genres": ["romcom", "erotica"],
        "through_line": "Герой учится принимать себя",
        "threads": [
            {
                "name": "размер/секрет",
                "characters": ["Совёнок", "Алиса"],
                "min_steps": 2,
                "max_steps": 4,
            }
        ],
        "tropes": ["secret_reveal"],
        "pivot": "Секрет выходит наружу",
        "tone_curve": ["comedy", "drama"],
    }
    payload.update(overrides)
    return payload


class TestShapesLibrary:
    def test_catalog_lists_every_shape(self):
        adult_catalog = render_shape_catalog(adult=True)

        for slug in STORY_SHAPES:
            assert f"- {slug}:" in adult_catalog

    def test_catalog_hides_adult_shapes_for_default(self):
        default_catalog = render_shape_catalog()

        for slug, shape in STORY_SHAPES.items():
            if shape.adult_only:
                assert f"- {slug}:" not in default_catalog
            else:
                assert f"- {slug}:" in default_catalog

    def test_block_keeps_beat_order(self):
        block = render_shape_block("relationship_arc")

        positions = [
            block.index("1. Encounter"),
            block.index("2. Attraction"),
            block.index("3. Deepening"),
            block.index("4. Complication"),
            block.index("5. Rupture"),
            block.index("6. Repair"),
            block.index("7. Commitment"),
        ]
        assert positions == sorted(positions)

    def test_block_has_layout_notes(self):
        shape = STORY_SHAPES["hero_cycle"]
        block = render_shape_block("hero_cycle")

        assert shape.step_note in block
        assert shape.conflict_note in block

    def test_unknown_slug_falls_back_to_default_shape(self):
        assert render_shape_block("no_such_shape") == render_shape_block(DEFAULT_SHAPE)

    def test_block_includes_heat_note_only_for_adult(self):
        block_default = render_shape_block("relationship_arc")
        block_adult = render_shape_block("relationship_arc", adult=True)

        assert "Heat distribution:" not in block_default
        assert "Heat distribution:" in block_adult

    def test_erotic_escalation_is_adult_only(self):
        shape = STORY_SHAPES["erotic_escalation"]

        assert shape.adult_only is True
        assert shape.heat_note


class TestParseDesign:
    def test_keeps_valid_payload(self):
        design = parse_design(_payload(), CAST)

        assert design.shape == "relationship_arc"
        assert design.genres == ["romcom", "erotica"]
        assert design.through_line == "Герой учится принимать себя"
        assert design.tropes == ["secret_reveal"]
        assert design.pivot == "Секрет выходит наружу"
        assert design.tone_curve == ["comedy", "drama"]
        assert design.threads == [
            PlotThread(
                name="размер/секрет",
                characters=["Совёнок", "Алиса"],
                min_steps=2,
                max_steps=4,
            )
        ]

    def test_unknown_shape_falls_back(self):
        assert parse_design(_payload(shape="space_opera"), CAST).shape == DEFAULT_SHAPE
        assert parse_design(_payload(shape=""), CAST).shape == DEFAULT_SHAPE
        assert parse_design(_payload(shape=None), CAST).shape == DEFAULT_SHAPE

    def test_shape_is_normalized(self):
        assert parse_design(_payload(shape=" Farce "), CAST).shape == "farce"

    def test_no_threads_raises(self):
        for threads in (None, [], "nope"):
            try:
                parse_design(_payload(threads=threads), CAST)
            except GenerationError as e:
                assert "no threads" in str(e)
            else:  # pragma: no cover
                raise AssertionError("expected GenerationError")

    def test_thread_without_name_dropped(self):
        design = parse_design(
            _payload(
                threads=[
                    {"name": "  ", "characters": ["Алиса"], "min_steps": 1, "max_steps": 2},
                    {"name": "ревность", "characters": ["Алиса"], "min_steps": 1, "max_steps": 2},
                ]
            ),
            CAST,
        )

        assert [t.name for t in design.threads] == ["ревность"]

    def test_unknown_characters_dropped(self):
        design = parse_design(
            _payload(
                threads=[
                    {
                        "name": "нить",
                        "characters": ["Алиса", "Никто", "алиса"],
                        "min_steps": 1,
                        "max_steps": 2,
                    }
                ]
            ),
            CAST,
        )

        # остаётся каноническое имя из каста, дубль по регистру отбрасывается
        assert design.threads[0].characters == ["Алиса"]

    def test_thread_budget_normalized(self):
        design = parse_design(
            _payload(
                threads=[
                    {"name": "a", "characters": [], "min_steps": 0, "max_steps": 1},
                    {"name": "b", "characters": [], "min_steps": "3", "max_steps": 1},
                    {"name": "c", "characters": [], "min_steps": None, "max_steps": None},
                ]
            ),
            CAST,
        )

        budgets = [(t.min_steps, t.max_steps) for t in design.threads]
        assert budgets == [(1, 2), (3, 4), (1, 2)]

    def test_empty_list_items_dropped(self):
        design = parse_design(_payload(genres=["romcom", "", "  "]), CAST)

        assert design.genres == ["romcom"]
        assert design.tone_curve == ["comedy", "drama"]

    def test_missing_scalar_fields_become_empty(self):
        design = parse_design({"threads": [{"name": "a"}]}, CAST)

        assert design.genres == []
        assert design.tropes == []
        assert design.through_line == ""
        assert design.pivot == ""


class TestRenderPromptBlock:
    def test_block_contains_threads_and_budget(self):
        design = PlotDesign(
            shape="farce",
            genres=["comedy", "erotica"],
            through_line="Честность важнее репутации",
            threads=[
                PlotThread("секрет", ["Алиса", "Ольга"], 2, 4),
                PlotThread("роль Виолы", ["Совёнок"], 1, 3),
            ],
            tropes=["gossip_spreads"],
            pivot="Секрет раскрывается на вечеринке",
            tone_curve=["comedy", "tension", "resolve"],
        )

        block = design.render_prompt_block()

        assert "Chosen shape: farce" in block
        assert "Genres: comedy, erotica" in block
        assert "Through-line: Честность важнее репутации" in block
        assert "Pivot: Секрет раскрывается на вечеринке" in block
        assert "Tone curve: comedy, tension, resolve" in block
        assert "- секрет [2..4 steps] — characters: Алиса, Ольга" in block
        assert "- роль Виолы [1..3 steps] — characters: Совёнок" in block
        assert "Tropes (optional ingredients): gossip_spreads" in block
