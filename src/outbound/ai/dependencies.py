from typing import Annotated

from fastapi import Depends, Request
from openai import AsyncOpenAI

from src.core.codex.services import CodexService
from src.outbound.ai.codex_agent import CodexResearcher
from src.outbound.ai.deepseek_client import DeepSeekGenerator
from src.outbound.codex.dependencies import get_codex_service


def get_openai_client(request: Request) -> AsyncOpenAI:
    return request.app.state.openai_client


def get_deepseek_generator(
    client: Annotated[AsyncOpenAI, Depends(get_openai_client)],
) -> DeepSeekGenerator:
    return DeepSeekGenerator(client)

def get_codex_researcher(
    client: Annotated[AsyncOpenAI, Depends(get_openai_client)],
    codex_service: Annotated[CodexService, Depends(get_codex_service)],
) -> CodexResearcher:
    return CodexResearcher(client, codex_service)
