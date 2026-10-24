from src.core.novels.models import Novel, Scene
from src.core.novels.services.generation.generators.story_context import (
    MAX_KEY_FACTS,
    MAX_USED_PHRASES,
    StoryContextGenerator,
    StoryState,
    extract_used_phrases,
)


class TestStoryStateApply:
    def test_apply_adds_facts(self):
        state = StoryState()
        state.apply({"add_facts": ["Факт один", "Факт два"]})

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


class TestExtractUsedPhrases:
    def test_repeated_phrase_found(self):
        phrases = extract_used_phrases(
            ["Не ходи туда без меня", "Не ходи туда один"], ["Семён"]
        )

        assert "не ходи туда" in phrases

    def test_single_occurrence_ignored(self):
        assert extract_used_phrases(["Уникальная фраза здесь"], ["Семён"]) == []

    def test_phrase_with_cast_name_excluded(self):
        phrases = extract_used_phrases(["Семён пошёл", "Семён пошёл"], ["Семён"])

        assert phrases == []

    def test_limit_is_five(self):
        assert MAX_USED_PHRASES == 5


class TestStoryContextPrompt:
    def test_prompt_has_no_summary_or_used_phrases(self):
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

        content = prompt[0]["content"]
        assert "summary" not in content.lower()
        assert "used_phrases" not in content
        assert '"add_facts"' in content
        assert '"remove_facts"' in content
        assert '"characters"' in content


class TestStoryStateRender:
    def test_render_facts_and_characters_only(self):
        state = StoryState(
            key_facts=["Факт"],
            characters={"Лена": {"outfit": "пионерская форма"}},
        )

        rendered = state.render()

        assert "Important plot facts" in rendered
        assert "Character states" in rendered
        assert "Summary" not in rendered
        assert "Phrases already used" not in rendered

    def test_render_numbered_facts(self):
        state = StoryState(key_facts=["a", "b"])

        rendered = state.render(numbered=True)

        assert "1. a" in rendered
        assert "2. b" in rendered

    def test_load_old_plain_text(self):
        state = StoryState.load("Просто текст старого формата")

        assert state.key_facts == ["Просто текст старого формата"]
        assert state.characters == {}

    def test_dump_roundtrip(self):
        state = StoryState(
            key_facts=["f"],
            characters={"Лена": {"outfit": "пионерская форма"}},
        )

        loaded = StoryState.load(state.dump())

        assert loaded.key_facts == ["f"]
        assert loaded.characters == {"Лена": {"outfit": "пионерская форма"}}
