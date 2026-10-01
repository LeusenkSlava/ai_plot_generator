import httpx

from src.main.config.settings import settings

_client: httpx.AsyncClient | None = None


def build_codex_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.codex.BASE_URL,
            timeout=settings.codex.TIMEOUT,
        )
    return _client


async def close_codex_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
