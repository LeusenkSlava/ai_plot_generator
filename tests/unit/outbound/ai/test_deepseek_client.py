"""Тесты DeepSeekGenerator: парсинг JSON, обёртка ошибок, логирование."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIConnectionError, APIError

from src.outbound.ai.deepseek_client import DeepSeekGenerator


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
