import asyncio
import logging
import time
import uuid

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisLockError(RuntimeError):
    """Redis недоступен, блокировку не удалось захватить или истёк таймаут захвата."""


_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Продлевает TTL только если ключ всё ещё наш (значение == token). Если лок
# истёк и его перехватил другой воркер (другой token) — не трогаем чужой ключ.
_RENEW_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""


async def _release(client: aioredis.Redis, key: str, token: str) -> None:
    """Снимает блокировку, только если её значение совпадает с нашим токеном."""
    try:
        await client.eval(_RELEASE_SCRIPT, 1, key, token)
    except aioredis.RedisError as e:
        # Снять не смогли — не фатально: лок доживёт до TTL и освободится сам.
        logger.warning("Redis lock release failed for %r: %s", key, e)


class _LockRenewer:
    """Фоновая задача продления TTL, пока воркер держит блокировку.

    TTL больше не обязан покрывать всю генерацию: watchdog продлевает его каждые
    ``ttl/3`` секунд, поэтому TTL задаёт лишь время обнаружения упавшего воркера.
    Если ключ перехвачен другим воркером (token не совпал) — продление прекращается.
    """

    def __init__(self, client: aioredis.Redis, ttl_s: int):
        self._client = client
        self._ttl_s = ttl_s
        self._interval_s = max(ttl_s // 3, 1)
        self._tasks: dict[tuple, asyncio.Task] = {}

    def start(self, key: str, token: str) -> None:
        async def renew() -> None:
            while True:
                await asyncio.sleep(self._interval_s)
                try:
                    renewed = await self._client.eval(
                        _RENEW_SCRIPT, 1, key, token, self._ttl_s
                    )
                except aioredis.RedisError as e:
                    logger.warning("Redis lock renew failed for %r: %s", key, e)
                    return
                if not renewed:
                    # Мы потеряли лок (TTL истёк и его перехватили) — продлевать нечего.
                    return

        self._tasks[(key, token)] = asyncio.create_task(renew())

    async def stop(self, key: str, token: str) -> None:
        task = self._tasks.pop((key, token), None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class RedisJobLock:
    """Блокировка по ``job_id``. ``acquire`` неблокирующий: ``False`` = лок занят."""

    def __init__(self, client: aioredis.Redis, ttl_s: int):
        self._client = client
        self._ttl_s = ttl_s
        self._tokens: dict[int, str] = {}
        self._renewer = _LockRenewer(client, ttl_s)

    @staticmethod
    def _key(job_id: int) -> str:
        return f"gen:job:{job_id}"

    async def acquire(self, job_id: int) -> bool:
        token = uuid.uuid4().hex
        try:
            ok = await self._client.set(
                self._key(job_id), token, nx=True, ex=self._ttl_s
            )
        except aioredis.RedisError as e:
            raise RedisLockError(f"Redis job lock acquire failed: {e}") from e
        if ok:
            self._tokens[job_id] = token
            self._renewer.start(self._key(job_id), token)
            return True
        return False

    async def release(self, job_id: int) -> None:
        token = self._tokens.pop(job_id, None)
        if token is None:
            return
        await self._renewer.stop(self._key(job_id), token)
        await _release(self._client, self._key(job_id), token)


class RedisSceneLock:
    """Блокировка генерации сцены по ``(novel_id, roadmap_id, position)``.

    ``acquire`` блокирующий с таймаутом — повторяет старую семантику
    ``pg_advisory_xact_lock``, но без удержания транзакции/соединения Postgres.
    """

    def __init__(
        self,
        client: aioredis.Redis,
        ttl_s: int,
        acquire_timeout_s: float,
        poll_interval_s: float,
    ):
        self._client = client
        self._ttl_s = ttl_s
        self._acquire_timeout_s = acquire_timeout_s
        self._poll_interval_s = poll_interval_s
        self._tokens: dict[tuple[int, int, int], str] = {}
        self._renewer = _LockRenewer(client, ttl_s)

    @staticmethod
    def _key(novel_id: int, roadmap_id: int, position: int) -> str:
        return f"gen:scene:{novel_id}:{roadmap_id}:{position}"

    async def acquire(self, novel_id: int, roadmap_id: int, position: int) -> None:
        key = self._key(novel_id, roadmap_id, position)
        token = uuid.uuid4().hex
        deadline = time.monotonic() + self._acquire_timeout_s
        while True:
            try:
                ok = await self._client.set(key, token, nx=True, ex=self._ttl_s)
            except aioredis.RedisError as e:
                raise RedisLockError(
                    f"Redis scene lock acquire failed for {key!r}: {e}"
                ) from e
            if ok:
                self._tokens[(novel_id, roadmap_id, position)] = token
                self._renewer.start(key, token)
                return
            if time.monotonic() >= deadline:
                raise RedisLockError(
                    f"Timed out acquiring scene lock {key!r} "
                    f"after {self._acquire_timeout_s:.0f}s"
                )
            await asyncio.sleep(self._poll_interval_s)

    async def release(self, novel_id: int, roadmap_id: int, position: int) -> None:
        key = self._key(novel_id, roadmap_id, position)
        token = self._tokens.pop((novel_id, roadmap_id, position), None)
        if token is None:
            return
        await self._renewer.stop(key, token)
        await _release(self._client, key, token)

    async def is_locked(self, novel_id: int, roadmap_id: int, position: int) -> bool:
        try:
            return bool(
                await self._client.exists(self._key(novel_id, roadmap_id, position))
            )
        except aioredis.RedisError as e:
            # Только статус «generating» в плейбеке — деградируем в «не занято».
            logger.warning(
                "Redis scene lock is_locked(%s, %s, %s) failed: %s",
                novel_id,
                roadmap_id,
                position,
                e,
            )
            return False


class RedisBranchLock:
    """Блокировка ленивой генерации ветки по ``(novel_id, roadmap_choice_id)``.

    ``acquire`` блокирующий с таймаутом — повторяет семантику RedisSceneLock, но для
    генерации роадмапа ветки (ключ — вариант выбора, а не позиция сцены).
    """

    def __init__(
        self,
        client: aioredis.Redis,
        ttl_s: int,
        acquire_timeout_s: float,
        poll_interval_s: float,
    ):
        self._client = client
        self._ttl_s = ttl_s
        self._acquire_timeout_s = acquire_timeout_s
        self._poll_interval_s = poll_interval_s
        self._tokens: dict[tuple[int, int], str] = {}
        self._renewer = _LockRenewer(client, ttl_s)

    @staticmethod
    def _key(novel_id: int, roadmap_choice_id: int) -> str:
        return f"gen:branch:{novel_id}:{roadmap_choice_id}"

    async def acquire(self, novel_id: int, roadmap_choice_id: int) -> None:
        key = self._key(novel_id, roadmap_choice_id)
        token = uuid.uuid4().hex
        deadline = time.monotonic() + self._acquire_timeout_s
        while True:
            try:
                ok = await self._client.set(key, token, nx=True, ex=self._ttl_s)
            except aioredis.RedisError as e:
                raise RedisLockError(
                    f"Redis branch lock acquire failed for {key!r}: {e}"
                ) from e
            if ok:
                self._tokens[(novel_id, roadmap_choice_id)] = token
                self._renewer.start(key, token)
                return
            if time.monotonic() >= deadline:
                raise RedisLockError(
                    f"Timed out acquiring branch lock {key!r} "
                    f"after {self._acquire_timeout_s:.0f}s"
                )
            await asyncio.sleep(self._poll_interval_s)

    async def release(self, novel_id: int, roadmap_choice_id: int) -> None:
        key = self._key(novel_id, roadmap_choice_id)
        token = self._tokens.pop((novel_id, roadmap_choice_id), None)
        if token is None:
            return
        await self._renewer.stop(key, token)
        await _release(self._client, key, token)
