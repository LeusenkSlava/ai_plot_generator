"""Kafka-команда генерации: author_id из сообщения доходит до use case."""

import json
from contextlib import asynccontextmanager

import pytest

from src.inbound.kafka.handlers import plot_generation
from src.inbound.kafka.handlers.plot_generation import NovelGenerateHandler


class _RecordingResults:
    def __init__(self) -> None:
        self.sent: list[object] = []
        self.failed: list[tuple[int, str]] = []

    async def send_job(self, job) -> None:
        self.sent.append(job)

    async def send_failed(self, job_id: int, error: str) -> None:
        self.failed.append((job_id, error))


class _RecordingUseCase:
    def __init__(self, calls: list[dict]) -> None:
        self._calls = calls

    async def execute(self, **kwargs):
        self._calls.append(kwargs)
        return "job-result"


class _FakeSession:
    """Handler передаёт ``session.begin`` как фабрику транзакций."""

    def begin(self):
        return None


@asynccontextmanager
async def _fake_session_scope():
    yield _FakeSession()


@pytest.fixture
def calls(monkeypatch) -> list[dict]:
    monkeypatch.setattr(
        plot_generation, "get_session_scope", _fake_session_scope
    )
    return []


async def test_author_id_forwarded_from_message(calls):
    results = _RecordingResults()
    handler = NovelGenerateHandler(
        results=results,
        use_case_factory=lambda _session: _RecordingUseCase(calls),
    )
    raw = json.dumps(
        {"job_id": 5, "prompt": "история", "author_id": 42}
    ).encode()

    await handler.handle(raw)

    assert calls[0]["author_id"] == 42
    assert calls[0]["job_id"] == 5
    assert results.sent == ["job-result"]


async def test_old_message_without_author_is_accepted(calls):
    """Старые сообщения без author_id не должны падать в DLQ."""
    results = _RecordingResults()
    handler = NovelGenerateHandler(
        results=results,
        use_case_factory=lambda _session: _RecordingUseCase(calls),
    )
    raw = json.dumps({"job_id": 6, "prompt": "история"}).encode()

    await handler.handle(raw)

    assert calls[0]["author_id"] is None
    assert results.failed == []


async def test_invalid_message_reports_failure(calls):
    results = _RecordingResults()
    handler = NovelGenerateHandler(
        results=results,
        use_case_factory=lambda _session: _RecordingUseCase(calls),
    )

    await handler.handle(json.dumps({"job_id": 7, "prompt": ""}).encode())

    assert calls == []
    assert results.failed
    assert results.failed[0][0] == 7
