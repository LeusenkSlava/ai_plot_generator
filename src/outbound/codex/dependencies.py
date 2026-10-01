from typing import Annotated

import httpx
from fastapi import Depends, Request

from src.core.codex.services import CodexService
from src.outbound.codex.codex_client import HttpCodexClient


def get_codex_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.codex_client


def get_codex_service(
    client: Annotated[httpx.AsyncClient, Depends(get_codex_http_client)],
) -> CodexService:
    return CodexService(HttpCodexClient(client))
