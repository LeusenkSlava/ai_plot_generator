from src.core.novels.services.generate.story_context import (
    MAX_KEY_FACTS,
    MAX_USED_PHRASES,
    StoryState,
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

        assert "Краткое содержание" in rendered
        assert "Уже звучавшие фразы" in rendered
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
