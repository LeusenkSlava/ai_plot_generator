"""Юнит-тесты классификатора и детерминированных фиксов DialogueRepairService."""

import pytest

from src.core.novels.services.generation.assets import SceneAssetService
from src.core.novels.services.generation.generators.dialogue_repair import (
    DefectKind,
    DialogueRepairService,
)
from tests.factories import dialogue_line_domain
from tests.fakes.outbound.ai.generator import FakeGenerator
from tests.fakes.outbound.codex.client import FakeCodexService


@pytest.fixture
def repair() -> DialogueRepairService:
    return DialogueRepairService(
        generator=FakeGenerator(), scene_assets=SceneAssetService(FakeCodexService())
    )


def _line(name: str, text: str) -> dict:
    return {"character_name": name, "text": text}


VALID_NAMES = ["Алиса", "Боб"]


class TestClassify:
    def test_empty_lines_is_no_lines(self, repair):
        defects = repair.classify([], VALID_NAMES)
        assert [d.kind for d in defects] == [DefectKind.NO_LINES]

    def test_valid_lines_have_no_defects(self, repair):
        assert repair.classify(
            [_line("Алиса", "Я найду брата!"), _line("Боб", "Я пойду с тобой.")],
            VALID_NAMES,
        ) == []

    def test_unknown_character(self, repair):
        defects = repair.classify([_line("Незнакомец", "Кто я?")], VALID_NAMES)
        assert defects[0].kind is DefectKind.UNKNOWN_CHARACTER
        assert defects[0].line_index == 0

    def test_empty_text(self, repair):
        defects = repair.classify([_line("Алиса", "  ")], VALID_NAMES)
        assert defects[0].kind is DefectKind.EMPTY_TEXT

    def test_duplicate_line(self, repair):
        defects = repair.classify(
            [_line("Алиса", "Пойдём."), _line("Боб", "Пойдём.")], VALID_NAMES
        )
        kinds = [d.kind for d in defects]
        assert kinds == [DefectKind.DUPLICATE_LINE]
        assert defects[0].line_index == 1  # повтор — вторая строка

    def test_truncated_end(self, repair):
        defects = repair.classify(
            [_line("Алиса", "Я найду брата!"), _line("Боб", "Мы пойдём вместе и")],
            VALID_NAMES,
        )
        truncated = [d for d in defects if d.kind is DefectKind.TRUNCATED_END]
        assert len(truncated) == 1
        assert truncated[0].line_index == 1

    def test_interrupted_speech_not_truncated(self, repair):
        # Реплика, обрывающаяся тире (прерванная речь), — не оборванная.
        defects = repair.classify(
            [_line("Алиса", "Я не хочу об этом —")],
            VALID_NAMES,
        )
        assert [d.kind for d in defects] == []

    def test_name_with_whitespace_is_valid(self, repair):
        # «Алиса » с хвостовым пробелом не должна считаться неизвестным персонажем.
        defects = repair.classify(
            [_line("Алиса ", "Привет.")],
            VALID_NAMES,
        )
        assert [d.kind for d in defects] == []

    def test_duplicate_against_previous_scene(self, repair):
        previous = [dialogue_line_domain(text="Я найду брата!")]
        defects = repair.classify([_line("Алиса", "Я найду брата!")], VALID_NAMES, previous)
        assert defects[0].kind is DefectKind.DUPLICATE_LINE


class TestDeterministicFixes:
    def test_drop_empty_and_duplicates(self, repair):
        lines = [
            _line("Алиса", "Я найду брата!"),
            _line("Боб", ""),
            _line("Алиса", "Я найду брата!"),
            _line("Боб", "Я пойду с тобой."),
        ]
        kept = repair._drop_empty_and_duplicates(lines, None)
        assert [l["text"] for l in kept] == ["Я найду брата!", "Я пойду с тобой."]

    def test_fuzzy_name_exact_casefold(self, repair):
        assert repair._fuzzy_name("алиса", VALID_NAMES) == "Алиса"

    def test_fuzzy_name_close_match(self, repair):
        assert repair._fuzzy_name("Алисаа", VALID_NAMES) == "Алиса"

    def test_fuzzy_name_no_match(self, repair):
        assert repair._fuzzy_name("Злодей", VALID_NAMES) is None

    def test_fuzzy_remap_names(self, repair):
        lines = [_line("алиса", "Привет."), _line("Боб", "Привет.")]
        repair._fuzzy_remap_names(lines, VALID_NAMES)
        assert lines[0]["character_name"] == "Алиса"
        assert lines[1]["character_name"] == "Боб"

    def test_index_by_field(self, repair):
        items = [
            {"index": 2, "text": "b"},
            {"index": 1, "text": "a"},
            "not-a-dict",
            {"text": "no-index"},
        ]
        assert repair._index_by_field(items, "index") == {
            2: {"index": 2, "text": "b"},
            1: {"index": 1, "text": "a"},
        }

    def test_pick_tag_fallback_normal_then_first(self, repair):
        assert repair._pick_tag({"emotion_base_tag": "angry"}, ["normal", "angry"], []) == (
            "angry",
            [],
        )
        # невалидный slug → fallback на normal
        assert repair._pick_tag(
            {"emotion_base_tag": "made-up"}, ["normal", "angry"], []
        ) == ("normal", [])
        # нет normal → первый slug
        assert repair._pick_tag(
            {"emotion_base_tag": "made-up"}, ["angry", "calm"], []
        ) == ("angry", [])


class TestRepairLines:
    async def test_valid_lines_pass_through(self, repair):
        result = await repair.repair_lines(
            [_line("Алиса", "Я найду брата!"), _line("Боб", "Я пойду с тобой.")],
            VALID_NAMES,
        )
        assert not result.has_unfixable
        assert [l["text"] for l in result.lines_data] == [
            "Я найду брата!",
            "Я пойду с тобой.",
        ]

    async def test_empty_is_unfixable(self, repair):
        result = await repair.repair_lines([], VALID_NAMES)
        assert result.has_unfixable
        assert result.unfixable[0].kind is DefectKind.NO_LINES

    async def test_duplicates_deduped_without_llm(self, repair):
        generator = repair._generator
        result = await repair.repair_lines(
            [
                _line("Алиса", "Пойдём."),
                _line("Боб", "Пойдём."),
                _line("Алиса", "Стой!"),
            ],
            VALID_NAMES,
        )
        assert [l["text"] for l in result.lines_data] == ["Пойдём.", "Стой!"]
        assert generator.call_count == 0  # дедуп детерминированный

    async def test_unknown_name_fuzzy_remapped_without_llm(self, repair):
        generator = repair._generator
        result = await repair.repair_lines([_line("алиса", "Привет!")], VALID_NAMES)
        assert not result.has_unfixable
        assert result.lines_data[0]["character_name"] == "Алиса"
        assert generator.call_count == 0

    async def test_name_whitespace_trimmed_without_llm(self, repair):
        generator = repair._generator
        result = await repair.repair_lines([_line("  Алиса ", "Привет!")], VALID_NAMES)
        assert not result.has_unfixable
        assert result.lines_data[0]["character_name"] == "Алиса"
        assert generator.call_count == 0

    async def test_unknown_name_repaired_by_llm(self, repair):
        generator = repair._generator
        generator.returns(
            {"fixes": [{"index": 1, "character_name": "Алиса", "text": "Кто я?"}]}
        )
        result = await repair.repair_lines([_line("Незнакомец", "Кто я?")], VALID_NAMES)
        assert not result.has_unfixable
        assert result.lines_data[0]["character_name"] == "Алиса"
        assert generator.call_count == 1

    async def test_unknown_name_unfixable_after_llm(self, repair):
        generator = repair._generator
        # LLM возвращает снова неверное имя → остаётся неисправимым.
        generator.returns(
            {"fixes": [{"index": 1, "character_name": "Злодей", "text": "Кто я?"}]}
        )
        result = await repair.repair_lines([_line("Незнакомец", "Кто я?")], VALID_NAMES)
        assert result.has_unfixable
        assert result.unfixable[0].kind is DefectKind.UNKNOWN_CHARACTER

    async def test_truncated_end_completed_by_llm(self, repair):
        generator = repair._generator
        generator.returns(
            {
                "fixes": [
                    {"index": 1, "character_name": "Боб", "text": "Мы пойдём и найдём его."}
                ]
            }
        )
        result = await repair.repair_lines(
            [_line("Алиса", "Я найду брата!"), _line("Боб", "Мы пойдём и")],
            VALID_NAMES,
        )
        assert not result.has_unfixable
        assert result.lines_data[-1]["text"] == "Мы пойдём и найдём его."
        assert generator.call_count == 1

    async def test_truncated_end_unfixable_after_llm(self, repair):
        generator = repair._generator
        # LLM «дописал» реплику, но снова без пунктуации конца → остаётся неисправимым.
        generator.returns(
            {"fixes": [{"index": 1, "character_name": "Боб", "text": "Мы пойдём и"}]}
        )
        result = await repair.repair_lines(
            [_line("Алиса", "Я найду брата!"), _line("Боб", "Мы пойдём и")],
            VALID_NAMES,
        )
        assert result.has_unfixable
        assert result.unfixable[0].kind is DefectKind.TRUNCATED_END
