from typing import Annotated

from fastapi import Depends, Request
from openai import AsyncOpenAI

from src.outbound.ai.deepseek_client import DeepSeekNovelGenerator


def get_openai_client(request: Request) -> AsyncOpenAI:
    return request.app.state.openai_client


def get_deepseek_generator(
    client: Annotated[AsyncOpenAI, Depends(get_openai_client)],
) -> DeepSeekNovelGenerator:
    return DeepSeekNovelGenerator(client)
