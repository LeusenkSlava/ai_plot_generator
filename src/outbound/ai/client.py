from openai import AsyncOpenAI

from src.main.config.settings import settings

_client: AsyncOpenAI | None = None


def build_deepseek_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.deepseek.API_KEY,
            base_url=settings.deepseek.BASE_URL,
        )
    return _client


async def close_deepseek_client() -> None:
    if _client is not None:
        await _client.close()
