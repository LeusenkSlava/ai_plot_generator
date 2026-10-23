import pytest

from src.core.novels.models import Novel, Scene
from src.core.novels.services.generation.generators.story_context import (
    MAX_KEY_FACTS,
    MAX_USED_PHRASES,
    StoryContextGenerator,
    StoryState,
    _cast_name_tokens,
    _filter_used_phrases,
    _valid_used_phrase,
)


class TestStoryStateApply:
    def test_apply_summary_and_facts(self):
        state = StoryState()
        state.apply(
            {
                "summary": "Сюжет сдвинулся.",
                "add_facts": ["Факт один", "Факт два"],
            }
        )

        assert state.summary == "Сюжет сдвинулся."
        assert state.key_facts == ["Факт один", "Факт два"]

    def test_remove_facts_by_number(self):
        state = StoryState(key_facts=["a", "b", "c"])
        state.apply({"remove_facts": [2]})

        assert state.key_facts == ["a", "c"]

    def test_exact_duplicate_fact_skipped(self):
        state = StoryState(key_facts=["Лена попросила не ходить без неё"])
        state.apply({"add_facts": ["Лена попросила не ходить без неё"]})

        assert state.key_facts == ["Лена попросила не ходить без неё"]

    def test_duplicate_ignores_case_and_punctuation(self):
        state = StoryState(key_facts=["Лена попросила: не ходить без неё!"])
        state.apply({"add_facts": ["лена попросила не ходить без неё"]})

        assert len(state.key_facts) == 1

    def test_contained_fact_skipped(self):
        state = StoryState(key_facts=["Семён приехал в лагерь на автобусе"])
        state.apply({"add_facts": ["Семён приехал в лагерь"]})

        assert state.key_facts == ["Семён приехал в лагерь на автобусе"]

    def test_new_fact_absorbs_existing(self):
        state = StoryState(key_facts=["Семён приехал в лагерь"])
        state.apply({"add_facts": ["Семён приехал в лагерь на автобусе вечером"]})

        assert state.key_facts == ["Семён приехал в лагерь на автобусе вечером"]

    def test_facts_trimmed_to_max(self):
        state = StoryState(key_facts=[f"Факт {i}" for i in range(MAX_KEY_FACTS)])
        state.apply({"add_facts": ["Новый факт"]})

        assert len(state.key_facts) == MAX_KEY_FACTS
        # Самый старый факт уходит первым
        assert state.key_facts[0] == "Факт 1"
        assert state.key_facts[-1] == "Новый факт"


class TestStoryStateFreshFactProtection:
    def test_fresh_fact_not_removed_next_iteration(self):
        """Только что добавленный факт не удаляется на следующей итерации."""
        state = StoryState()
        state.apply({"add_facts": ["Семён проспал линейку"]})

        protected = state.apply({"remove_facts": [1]})

        assert state.key_facts == ["Семён проспал линейку"]
        assert protected == [(1, "Семён проспал линейку")]

    def test_fact_removable_only_after_min_age(self):
        """Факт можно удалить только после MIN_FACT_AGE_TO_REMOVE итераций."""
        state = StoryState()
        state.apply({"add_facts": ["Факт"]})

        # возраст 0 — защищён
        assert state.apply({"remove_facts": [1]}) == [(1, "Факт")]
        # возраст 1 — защищён
        assert state.apply({"remove_facts": [1]}) == [(1, "Факт")]
        assert state.key_facts == ["Факт"]
        # возраст 2 — удаляем
        assert state.apply({"remove_facts": [1]}) == []
        assert state.key_facts == []

    def test_old_fact_removed_normally(self):
        """Факт без возраста (legacy/прямая конструкция) считается взрослым и удаляется."""
        state = StoryState(key_facts=["старый факт"])

        assert state.apply({"remove_facts": [1]}) == []
        assert state.key_facts == []

    def test_ages_survive_dump_roundtrip(self):
        """Возраста фактов сохраняются в JSON и защита работает между сценами."""
        state = StoryState()
        state.apply({"add_facts": ["Факт"]})

        loaded = StoryState.load(state.dump())

        assert loaded.fact_ages == [0]
        assert loaded.apply({"remove_facts": [1]}) == [(1, "Факт")]


class TestUsedPhrasesValidation:
    def test_single_word_rejected(self):
        tokens = _cast_name_tokens(["Семён", "Виола"])

        assert _valid_used_phrase("наверное", tokens) is False
        assert _valid_used_phrase("пионер", tokens) is False

    def test_two_or_more_words_accepted(self):
        tokens = _cast_name_tokens(["Семён", "Виола"])

        assert _valid_used_phrase("не ходи туда", tokens) is True

    def test_phrase_with_cast_name_rejected(self):
        tokens = _cast_name_tokens(["Семён", "Ольга Дмитриевна"])

        assert _valid_used_phrase("Ольга Дмитриевна", tokens) is False
        assert _valid_used_phrase("Ульяна не глупая", _cast_name_tokens(["Ульяна"])) is False

    def test_filter_drops_invalid(self):
        tokens = _cast_name_tokens(["Семён", "Виола", "Ольга Дмитриевна"])

        result = _filter_used_phrases(
            ["наверное", "не ходи туда", "Ольга Дмитриевна"], tokens
        )

        assert result == ["не ходи туда"]

    def test_cast_name_tokens_split_multiword(self):
        tokens = _cast_name_tokens(["Ольга Дмитриевна"])

        assert tokens == {"ольга", "дмитриевна"}


class TestUsedPhrasesLimit:
    def test_limit_is_five(self):
        assert MAX_USED_PHRASES == 5

    def test_prompt_uses_constant(self):
        novel = Novel(
            id=1,
            created_at=None,
            updated_at=None,
            title="Т",
            public_description="",
            description="D",
            tone="tone",
        )
        scene = Scene(
            id=1,
            created_at=None,
            updated_at=None,
            roadmap_id=1,
            title="Сцена",
            description="Описание",
            order=1,
        )
        gen = StoryContextGenerator.__new__(StoryContextGenerator)
        prompt = gen._StoryContextGenerator__create_prompt(
            novel, scene, [], [], StoryState()
        )

        assert f"up to {MAX_USED_PHRASES} motif phrases" in prompt[0]["content"]


class TestStoryStateUsedPhrases:
    def test_used_phrases_collected(self):
        state = StoryState()
        state.apply({"used_phrases": ["Не ходи туда без меня"]})

        assert state.used_phrases == ["Не ходи туда без меня"]

    def test_used_phrases_deduplicated(self):
        state = StoryState(used_phrases=["Не ходи туда без меня"])
        state.apply({"used_phrases": ["не ходи туда без меня"]})

        assert state.used_phrases == ["Не ходи туда без меня"]

    def test_used_phrases_trimmed_to_max(self):
        state = StoryState(used_phrases=[f"Фраза {i}" for i in range(MAX_USED_PHRASES)])
        state.apply({"used_phrases": ["Новая фраза"]})

        assert len(state.used_phrases) == MAX_USED_PHRASES
        assert state.used_phrases[-1] == "Новая фраза"


class TestStoryStateRender:
    def test_render_includes_used_phrases(self):
        state = StoryState(
            summary="Кратко.",
            key_facts=["Факт"],
            used_phrases=["Не ходи туда без меня"],
        )

        rendered = state.render()

        assert "Summary" in rendered
        assert "Phrases already used" in rendered
        assert "Не ходи туда без меня" in rendered

    def test_render_numbered_facts(self):
        state = StoryState(key_facts=["a", "b"])

        rendered = state.render(numbered=True)

        assert "1. a" in rendered
        assert "2. b" in rendered

    def test_load_old_plain_text(self):
        state = StoryState.load("Просто текст старого формата")

        assert state.summary == "Просто текст старого формата"
        assert state.key_facts == []

    def test_dump_roundtrip(self):
        state = StoryState(
            summary="s",
            key_facts=["f"],
            characters={"Лена": {"outfit": "пионерская форма"}},
            used_phrases=["p"],
        )

        loaded = StoryState.load(state.dump())

        assert loaded.summary == "s"
        assert loaded.key_facts == ["f"]
        assert loaded.characters == {"Лена": {"outfit": "пионерская форма"}}
        assert loaded.used_phrases == ["p"]
