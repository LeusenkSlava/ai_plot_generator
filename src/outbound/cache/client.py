import redis.asyncio as aioredis

from src.main.config.settings import settings

_client: aioredis.Redis | None = None


def build_redis_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.redis.URL,
            decode_responses=True,
        )
    return _client


async def close_redis_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
