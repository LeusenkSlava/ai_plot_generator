from collections.abc import Iterable
from dataclasses import dataclass, field

from aiokafka import TopicPartition


@dataclass
class _PartitionState:
    inflight: set[int] = field(default_factory=set)
    completed: set[int] = field(default_factory=set)
    next_commit: int | None = None


class OffsetTracker:
    """Водяной знак оффсетов для ручного коммита при параллельной обработке.

    Сообщения одной партиции обрабатываются конкурентно, поэтому коммитим не
    «после каждого», а только непрерывно завершённый префикс (watermark). Это
    сохраняет at-least-once: сообщение, потерянное при падении воркера, будет
    перечитано, а идемпотентность по ``job_id`` делает повтор безопасным.
    """

    def __init__(self) -> None:
        self._states: dict[TopicPartition, _PartitionState] = {}

    def mark_inflight(self, tp: TopicPartition, offset: int) -> None:
        state = self._states.setdefault(tp, _PartitionState())
        if state.next_commit is None:
            state.next_commit = offset
        state.inflight.add(offset)

    def mark_done(self, tp: TopicPartition, offset: int) -> None:
        state = self._states.get(tp)
        if state is None:
            # Партиция была отозвана при ребалансе: оффсет больше не наш,
            # а коммитить его не нужно. Воркер, который её обрабатывал, мог
            # завершиться уже после отзыва — просто игнорируем.
            return
        state.inflight.discard(offset)
        state.completed.add(offset)

    def reset(self, partitions: Iterable[TopicPartition]) -> None:
        """Сбрасывает состояние отозванных партиций перед ребалансом.

        Без этого ``next_commit`` остаётся «устаревшим»: после возврата партиции
        трекер ждал бы оффсеты, которые уже не будут перечитаны, коммиты по
        партиции замирали бы, а ``completed`` рос бы неограниченно.
        """
        for tp in partitions:
            self._states.pop(tp, None)

    def watermark(self, tp: TopicPartition) -> int | None:
        """Следующий оффсет, который безопасно закоммитить (None, если нечего)."""
        state = self._states.get(tp)
        if state is None or state.next_commit is None:
            return None
        while state.next_commit in state.completed:
            state.completed.discard(state.next_commit)
            state.next_commit += 1
        return state.next_commit
