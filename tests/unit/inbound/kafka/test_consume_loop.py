import asyncio
from dataclasses import dataclass

import pytest

from src.inbound.kafka.tasks.consume_loop import _routing_key, consume_loop
from src.outbound.kafka.topic import Topics


@dataclass(frozen=True)
class FakeMessage:
    topic: str
    partition: int
    offset: int
    value: bytes


class FakeConsumer:
    """Конечный стрим сообщений; после исчерпания блокируется, имитируя живой топик.

    Записи о коммитах сохраняются как ``(topic, partition, offset)``.
    """

    def __init__(self, messages: list[FakeMessage]) -> None:
        self._messages = list(messages)
        self._i = 0
        self.commits: list[tuple[str, int, int]] = []

    def __aiter__(self) -> "FakeConsumer":
        return self

    async def __anext__(self) -> FakeMessage:
        if self._i < len(self._messages):
            msg = self._messages[self._i]
            self._i += 1
            return msg
        # Живой стрим не заканчивается: блокируемся, тест сам отменит consume_loop.
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def commit(self, offsets: dict) -> None:
        for tp, offset in offsets.items():
            self.commits.append((tp.topic, tp.partition, offset))


async def _wait_until(pred, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not pred():
        if loop.time() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0)


def test_routing_key_returns_novel_id_for_scene_topic():
    raw = b'{"job_id": 1, "novel_id": 42, "scene_order": 2}'
    assert _routing_key(Topics.SCENE_GENERATE, raw) == 42


def test_routing_key_none_for_other_topics():
    assert _routing_key(Topics.NOVEL_GENERATE, b'{"novel_id": 42}') is None


def test_routing_key_none_for_invalid_scene_message():
    assert _routing_key(Topics.SCENE_GENERATE, b"not json") is None


async def test_consume_loop_commits_contiguous_prefix():
    topic = Topics.NOVEL_GENERATE
    messages = [
        FakeMessage(topic, 0, 0, b'{"job_id": 1}'),
        FakeMessage(topic, 0, 1, b'{"job_id": 2}'),
        FakeMessage(topic, 0, 2, b'{"job_id": 3}'),
    ]
    consumer = FakeConsumer(messages)
    processed: set[bytes] = set()

    async def handler(raw: bytes) -> None:
        processed.add(raw)
        await asyncio.sleep(0.001)

    task = asyncio.create_task(consume_loop(consumer, {topic: handler}, concurrency=2))

    await _wait_until(lambda: len(processed) == 3)
    await _wait_until(lambda: (topic, 0, 3) in consumer.commits)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert processed == {m.value for m in messages}
    # Водяной знак прошёл через весь непрерывный префикс 0..2.
    assert (topic, 0, 3) in consumer.commits


async def test_consume_loop_does_not_commit_cancelled_message():
    topic = Topics.NOVEL_GENERATE
    messages = [
        FakeMessage(topic, 0, 0, b'{"job_id": 1}'),
        FakeMessage(topic, 0, 1, b'{"job_id": 2}'),
    ]
    consumer = FakeConsumer(messages)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(raw: bytes) -> None:
        entered.set()
        await release.wait()  # воркер зависает, чтобы его отменили

    task = asyncio.create_task(consume_loop(consumer, {topic: handler}, concurrency=1))

    await asyncio.wait_for(entered.wait(), timeout=2)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Прерванное сообщение не должно быть закоммичено (иначе потеряется при рестарте).
    assert consumer.commits == []
