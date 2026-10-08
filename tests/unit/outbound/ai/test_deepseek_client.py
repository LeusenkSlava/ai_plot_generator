"""Тесты DeepSeekGenerator: парсинг JSON, обёртка ошибок, логирование."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIConnectionError, APIError

from src.outbound.ai.deepseek_client import DeepSeekGenerator, _is_truncated


def _llm_response(
    content: str, *, prompt_tokens: int = 10, completion_tokens: int = 20
) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.prompt_cache_hit_tokens = 0
    return response


@pytest.fixture
def openai_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sut(openai_client) -> DeepSeekGenerator:
    return DeepSeekGenerator(client=openai_client)


PROMPT = [{"role": "user", "content": "hi"}]


class TestDeepSeekGenerator:
    async def test_parses_json_response(self, sut, openai_client):
        openai_client.chat.completions.create.return_value = _llm_response(
            json.dumps({"title": "T", "tone": "dark"})
        )

        result = await sut.generate(PROMPT)

        assert result == {"title": "T", "tone": "dark"}

    async def test_invalid_json_raises_runtime_error(self, sut, openai_client):
        openai_client.chat.completions.create.return_value = _llm_response("not a json")

        with pytest.raises(RuntimeError, match="Invalid DeepSeek response format"):
            await sut.generate(PROMPT)

    async def test_api_error_wrapped(self, sut, openai_client):
        openai_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        with pytest.raises(RuntimeError, match="DeepSeek API error"):
            await sut.generate(PROMPT)

    async def test_api_error_logs_and_raises(self, sut, openai_client, monkeypatch):
        log_mock = MagicMock()
        monkeypatch.setattr("src.outbound.ai.deepseek_client.log_llm_call", log_mock)
        openai_client.chat.completions.create.side_effect = APIError(
            "boom", request=MagicMock(), body=None
        )

        with pytest.raises(RuntimeError):
            await sut.generate(PROMPT)

        log_mock.assert_called_once()
        assert log_mock.call_args.kwargs["error"] is not None

    async def test_success_logs_call(self, sut, openai_client, monkeypatch):
        log_mock = MagicMock()
        monkeypatch.setattr("src.outbound.ai.deepseek_client.log_llm_call", log_mock)
        openai_client.chat.completions.create.return_value = _llm_response(
            json.dumps({"title": "T"})
        )

        await sut.generate(PROMPT)

        log_mock.assert_called_once()
        kwargs = log_mock.call_args.kwargs
        assert kwargs["prompt_tokens"] == 10
        assert kwargs["completion_tokens"] == 20
        assert kwargs["response"] == json.dumps({"title": "T"})
        assert kwargs["error"] is None
        assert "json_repaired" not in kwargs["extra"]

    async def test_missing_comma_is_repaired_and_logged(self, sut, openai_client, monkeypatch):
        log_mock = MagicMock()
        monkeypatch.setattr("src.outbound.ai.deepseek_client.log_llm_call", log_mock)
        broken = '{\n  "title": "T"\n  "tone": "dark"\n}'
        openai_client.chat.completions.create.return_value = _llm_response(broken)

        result = await sut.generate(PROMPT)

        assert result == {"title": "T", "tone": "dark"}
        log_mock.assert_called_once()
        kwargs = log_mock.call_args.kwargs
        assert kwargs["error"] is None
        assert kwargs["extra"]["json_repaired"] is True
        # в лог пишется исходный (битый) ответ — как вернул LLM
        assert kwargs["response"] == broken

    async def test_unrepairable_json_logs_error_and_raises(self, sut, openai_client, monkeypatch):
        log_mock = MagicMock()
        monkeypatch.setattr("src.outbound.ai.deepseek_client.log_llm_call", log_mock)
        openai_client.chat.completions.create.return_value = _llm_response("not a json")

        with pytest.raises(RuntimeError, match="Invalid DeepSeek response format"):
            await sut.generate(PROMPT)

        log_mock.assert_called_once()
        assert log_mock.call_args.kwargs["error"] == "invalid json"
        assert "json_repaired" not in log_mock.call_args.kwargs["extra"]

    async def test_trailing_comma_is_repaired(self, sut, openai_client, monkeypatch):
        log_mock = MagicMock()
        monkeypatch.setattr("src.outbound.ai.deepseek_client.log_llm_call", log_mock)
        broken = '{"title": "T", "tone": "dark",}'
        openai_client.chat.completions.create.return_value = _llm_response(broken)

        result = await sut.generate(PROMPT)

        assert result == {"title": "T", "tone": "dark"}
        kwargs = log_mock.call_args.kwargs
        assert kwargs["error"] is None
        assert kwargs["extra"]["json_repaired"] is True

    async def test_truncated_json_not_repaired_raises(self, sut, openai_client, monkeypatch):
        # обрезанный ответ не долечиваем — уходит в ретрай
        log_mock = MagicMock()
        monkeypatch.setattr("src.outbound.ai.deepseek_client.log_llm_call", log_mock)
        openai_client.chat.completions.create.return_value = _llm_response('{"title": "T"')

        with pytest.raises(RuntimeError, match="Invalid DeepSeek response format"):
            await sut.generate(PROMPT)

        assert log_mock.call_args.kwargs["error"] == "invalid json"
        assert "json_repaired" not in log_mock.call_args.kwargs["extra"]


class TestIsTruncated:
    def test_unterminated_string(self):
        assert _is_truncated('{"title": "T')

    def test_unclosed_object(self):
        assert _is_truncated('{"title": "T"')

    def test_unclosed_array(self):
        assert _is_truncated('[1, 2')

    def test_complete_json_not_truncated(self):
        assert not _is_truncated('{"title": "T"}')
        assert not _is_truncated('[1, 2]')
        assert not _is_truncated('{\n  "title": "T"\n  "tone": "dark"\n}')

    def test_brace_inside_string_ignored(self):
        assert not _is_truncated('{"text": "a } b"}')
