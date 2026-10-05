from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class LLMTrace:
    novel_id: int | None = None
    operation: str = ""
    # Записи, сделанные до того, как стал известен novel_id (например, создание новеллы)
    pending: list[dict] = field(default_factory=list)

    def bind(self, novel_id: int) -> None:
        """Новелла создана: дальнейшие (и накопленные) записи относятся к ней."""
        self.novel_id = novel_id


_trace: ContextVar[LLMTrace | None] = ContextVar("llm_trace", default=None)
_step: ContextVar[str | None] = ContextVar("llm_step", default=None)
# Куда сбросить незаписанные записи при выходе из трассировки (outbound регистрирует writer)
_pending_sink: Callable[[LLMTrace], None] | None = None


def set_pending_sink(sink: Callable[[LLMTrace], None]) -> None:
    global _pending_sink
    _pending_sink = sink


@contextmanager
def llm_trace(operation: str, novel_id: int | None = None) -> Iterator[LLMTrace]:
    trace = LLMTrace(novel_id=novel_id, operation=operation)
    token = _trace.set(trace)
    try:
        yield trace
    finally:
        _trace.reset(token)
        if trace.pending and _pending_sink is not None:
            _pending_sink(trace)


@contextmanager
def llm_step(name: str) -> Iterator[None]:
    token = _step.set(name)
    try:
        yield
    finally:
        _step.reset(token)


def current_trace() -> LLMTrace | None:
    return _trace.get()


def current_step() -> str | None:
    return _step.get()
