import httpx
import pytest

from src.outbound.codex.codex_client import HttpCodexClient
from tests.unit.outbound.codex.constants import BASE_URL


@pytest.fixture
async def _http_client():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        yield client


@pytest.fixture
def sut(_http_client) -> HttpCodexClient:
    return HttpCodexClient(client=_http_client)
