"""Кэш поверх Redis для справочных данных Codex.

Кэш необязателен и не должен влиять на генерацию: при недоступности Redis
все операции тихо деградируют в «промах» (get -> None, set -> no-op).
"""

import logging
from typing import Protocol

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CacheProtocol(Protocol):
    """Минимальный асинхронный кэш «ключ -> сырая строка»."""

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_s: int) -> None: ...


class RedisCache:
    """Реализация CacheProtocol поверх redis.asyncio."""

    def __init__(self, client: aioredis.Redis):
        self._client = client

    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)
        except aioredis.RedisError as e:
            logger.warning(f"RedisCache.get({key!r}) failed: {e}")
            return None

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        try:
            await self._client.set(key, value, ex=ttl_s)
        except aioredis.RedisError as e:
            logger.warning(f"RedisCache.set({key!r}) failed: {e}")
