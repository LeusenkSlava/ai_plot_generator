import asyncio

from src.inbound.kafka.tasks.keyed_locks import KeyedLocks


async def test_serializes_same_key_in_fifo_order():
    locks = KeyedLocks()
    order: list[int] = []

    async def work(i: int) -> None:
        async def body() -> None:
            order.append(i)
            await asyncio.sleep(0.01)

        await locks.run_exclusive(1, body)

    await asyncio.gather(work(1), work(2), work(3))
    assert order == [1, 2, 3]


async def test_parallel_across_different_keys():
    locks = KeyedLocks()
    release = asyncio.Event()

    async def slow(i: int) -> None:
        async def body() -> None:
            await release.wait()

        await locks.run_exclusive(i, body)

    slow_task = asyncio.create_task(slow(1))
    # даём slow захватить лок ключа 1
    await asyncio.sleep(0)

    done = asyncio.Event()

    async def fast() -> None:
        async def body() -> None:
            done.set()

        await locks.run_exclusive(2, body)

    fast_task = asyncio.create_task(fast())
    # ключ 2 не блокируется ключом 1
    await asyncio.wait_for(done.wait(), timeout=1)

    release.set()
    await asyncio.gather(slow_task, fast_task)


async def test_lock_is_cleaned_up_when_idle():
    locks = KeyedLocks()
    await locks.run_exclusive(42, lambda: asyncio.sleep(0))
    assert 42 not in locks._locks
