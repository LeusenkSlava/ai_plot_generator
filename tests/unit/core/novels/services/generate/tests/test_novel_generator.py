import pytest

from src.core.novels.exceptions import GenerationError
from tests.factories import (
    background_domain,
    character_domain,
    universe_domain,
    valid_novel_llm_payload,
)

# ---------------------------------------------------------------------------
# Общая подготовка
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _default_llm_response(generator, valid_llm_payload):
    """По умолчанию LLM всегда возвращает валидный payload.

    Отдельные тесты могут переопределить поведение:
      - generator.returns(payload)   — конкретный ответ на конкретный вызов
      - generator.raises(error)      — ошибка на конкретный вызов

    Очередь в FakeGenerator имеет приоритет над always_returns,
    поэтому переопределение из тела теста сработает.
    """
    generator.always_returns(valid_llm_payload)


# ---------------------------------------------------------------------------
# Без universe_id — Codex не дёргается
# ---------------------------------------------------------------------------


class TestGenerateWithoutUniverse:
    async def test_codex_not_called(self, sut, codex):
        await sut.generate(user_prompt="про ведьму")

        assert codex.calls == []

    async def test_prompt_has_no_codex_context(self, sut, generator):
        await sut.generate(user_prompt="про ведьму")

        generator.assert_system_not_contains("существующей вселенной")
        assert generator.last_user_prompt == "про ведьму"

    async def test_prompt_is_two_messages(self, sut, generator):
        await sut.generate(user_prompt="моя идея")

        assert generator.last_prompt_roles == ["system", "user"]
        assert generator.last_user_prompt == "моя идея"

    async def test_system_prompt_contains_json_instruction(self, sut, generator):
        await sut.generate(user_prompt="x")

        generator.assert_system_contains(
            "сценарист интерактивных визуальных новелл",
            "json",
        )

    async def test_novel_saved_with_none_universe_id(self, sut, novel_service):
        result = await sut.generate(user_prompt="x")

        assert len(novel_service.saved) == 1
        assert result.universe_id is None
        assert result is novel_service.saved[0]

    async def test_llm_called_exactly_once(self, sut, generator):
        await sut.generate(user_prompt="x")

        assert generator.call_count == 1


# ---------------------------------------------------------------------------
# С universe_id — Codex вызывается и контекст попадает в промпт
# ---------------------------------------------------------------------------


class TestGenerateWithUniverse:
    UNIVERSE_ID = 1

    @pytest.fixture(autouse=True)
    def _seed_codex(self, codex):
        codex.add_universe(universe_domain(id=self.UNIVERSE_ID))
        codex.add_characters(
            self.UNIVERSE_ID,
            [
                character_domain(name="Алиса", description="Ведьма"),
                character_domain(id=2, slug="bob", name="Боб", description="Рыцарь"),
            ],
        )
        codex.add_backgrounds(
            self.UNIVERSE_ID,
            [
                background_domain(id=1, slug="forest", description="Лес"),
                background_domain(
                    id=2,
                    slug="castle",
                    description="Замок",
                    asset_key="bg/castle.png",
                ),
            ],
        )

    async def test_codex_called_with_universe_id(self, sut, codex):
        await sut.generate(user_prompt="x", universe_id=self.UNIVERSE_ID)

        assert codex.calls == [
            ("get_universe", self.UNIVERSE_ID),
            ("get_characters", self.UNIVERSE_ID),
            ("get_backgrounds", self.UNIVERSE_ID),
        ]

    async def test_codex_context_injected_into_system_prompt(self, sut, generator):
        await sut.generate(user_prompt="x", universe_id=self.UNIVERSE_ID)

        generator.assert_system_contains(
            "Мир Тьмы",
            "Мрачное средневековье",
            "Алиса: Ведьма",
            "Боб: Рыцарь",
            "Лес",
            "Замок",
            "ТОЛЬКО этих персонажей",
        )

    async def test_empty_characters_and_backgrounds(self, sut, codex, generator):
        codex.clear()

        await sut.generate(user_prompt="x", universe_id=self.UNIVERSE_ID)

        generator.assert_system_not_contains(
            "Персонажи (других нет):",
            "Локации (других нет):",
        )
        generator.assert_system_contains("Мир Тьмы")

    async def test_universe_id_saved_into_novel(self, sut, novel_service):
        result = await sut.generate(user_prompt="x", universe_id=self.UNIVERSE_ID)

        assert result.universe_id == self.UNIVERSE_ID
        assert novel_service.saved[0].universe_id == self.UNIVERSE_ID

    async def test_id_assigned_to_saved_novel(self, sut, novel_service):
        result = await sut.generate(user_prompt="x", universe_id=self.UNIVERSE_ID)

        assert result.id is not None
        assert result is novel_service.saved[0]

    async def test_universe_id_passed_through_not_hardcoded(self, sut, codex):
        """Проверяем, что код не хардкодит universe_id=1."""
        second_universe_id = 42
        codex.add_universe(universe_domain(id=second_universe_id))
        codex.add_characters(second_universe_id, [])
        codex.add_backgrounds(second_universe_id, [])

        await sut.generate(user_prompt="x", universe_id=second_universe_id)

        assert codex.calls == [
            ("get_universe", second_universe_id),
            ("get_characters", second_universe_id),
            ("get_backgrounds", second_universe_id),
        ]


# ---------------------------------------------------------------------------
# Взаимодействие с LLM — настраиваемое поведение
# ---------------------------------------------------------------------------


class TestLLMInteraction:
    async def test_specific_response_for_specific_call(self, sut, generator):
        """FakeGenerator позволяет задать ответ на конкретный вызов."""
        generator.returns(valid_novel_llm_payload(title="Особое название"))

        result = await sut.generate(user_prompt="x")

        assert result.title == "Особое название"

    async def test_two_generations_use_different_responses(self, sut, generator):
        """Очередь ответов работает между вызовами."""
        generator.returns(valid_novel_llm_payload(title="Первая"))
        generator.returns(valid_novel_llm_payload(title="Вторая"))

        first = await sut.generate(user_prompt="x")
        second = await sut.generate(user_prompt="y")

        assert first.title == "Первая"
        assert second.title == "Вторая"


# ---------------------------------------------------------------------------
# Обработка ошибок
# ---------------------------------------------------------------------------


class TestGenerateErrors:
    async def test_unknown_universe_raises(self, sut, generator):
        with pytest.raises(GenerationError, match="not found in Codex"):
            await sut.generate(user_prompt="x", universe_id=999)

        assert generator.not_called

    async def test_codex_failure_wrapped(self, sut, codex, generator):
        codex.fail_on("get_universe")

        with pytest.raises(GenerationError, match="Codex request failed"):
            await sut.generate(user_prompt="x", universe_id=1)

        assert generator.not_called

    async def test_llm_failure_wrapped_in_generation_error(self, sut, generator):
        generator.raises(RuntimeError("LLM down"))

        with pytest.raises(GenerationError, match="LLM down"):
            await sut.generate(user_prompt="x")

    async def test_llm_failure_preserves_cause(self, sut, generator):
        """Исходная ошибка LLM должна быть доступна через __cause__."""
        original = RuntimeError("LLM down")
        generator.raises(original)

        with pytest.raises(GenerationError) as exc_info:
            await sut.generate(user_prompt="x")

        assert exc_info.value.__cause__ is original

    async def test_save_failure_propagates(self, sut, novel_service):
        novel_service.raise_on_add = RuntimeError("DB down")

        with pytest.raises(RuntimeError, match="DB down"):
            await sut.generate(user_prompt="x")
