from aiokafka import TopicPartition

from src.inbound.kafka.tasks.offset_tracker import OffsetTracker


def _tp(partition: int = 0) -> TopicPartition:
    return TopicPartition("ai_plot.novel.generate", partition)


def test_watermark_waits_for_contiguous_prefix():
    tracker = OffsetTracker()
    p = _tp()

    tracker.mark_inflight(p, 0)
    tracker.mark_inflight(p, 1)
    tracker.mark_inflight(p, 2)

    # 1 и 2 готовы, но 0 ещё в полёте — коммитить нельзя
    tracker.mark_done(p, 1)
    tracker.mark_done(p, 2)
    assert tracker.watermark(p) == 0

    # 0 готов — можно коммитить непрерывный префикс 0..2
    tracker.mark_done(p, 0)
    assert tracker.watermark(p) == 3


def test_watermark_advances_only_in_order():
    tracker = OffsetTracker()
    p = _tp()

    tracker.mark_inflight(p, 10)
    tracker.mark_done(p, 10)
    assert tracker.watermark(p) == 11

    tracker.mark_inflight(p, 11)
    tracker.mark_inflight(p, 12)
    tracker.mark_done(p, 12)
    assert tracker.watermark(p) == 11  # 11 ещё не готов

    tracker.mark_done(p, 11)
    assert tracker.watermark(p) == 13


def test_watermark_none_without_messages():
    assert OffsetTracker().watermark(_tp()) is None


def test_partitions_are_independent():
    tracker = OffsetTracker()
    p0 = _tp(0)
    p1 = _tp(1)

    tracker.mark_inflight(p0, 0)
    tracker.mark_inflight(p1, 0)
    tracker.mark_done(p0, 0)

    assert tracker.watermark(p0) == 1
    assert tracker.watermark(p1) == 0  # p1 всё ещё в полёте


def test_reset_clears_partition_state():
    tracker = OffsetTracker()
    p = _tp()

    tracker.mark_inflight(p, 0)
    tracker.mark_done(p, 0)
    assert tracker.watermark(p) == 1

    # Ребаланс: партицию отозвали.
    tracker.reset([p])
    assert tracker.watermark(p) is None

    # После возврата партиции отсчёт начинается заново со свежего оффсета.
    tracker.mark_inflight(p, 5)
    tracker.mark_done(p, 5)
    assert tracker.watermark(p) == 6


def test_mark_done_ignores_revoked_partition():
    tracker = OffsetTracker()
    p = _tp()

    tracker.mark_inflight(p, 0)
    tracker.reset([p])

    # Воркер завершился уже после отзыва партиции — не падаем и не коммитим.
    tracker.mark_done(p, 0)
    assert tracker.watermark(p) is None
