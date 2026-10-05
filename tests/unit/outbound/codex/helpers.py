from typing import Any

import httpx
import respx


def mock_get_json(url: str, payload: Any, status: int = 200) -> respx.Route:
    """Успешный ответ с JSON-payload (dict или list)."""
    return respx.get(url).mock(return_value=httpx.Response(status, json=payload))


def mock_get_status(url: str, status: int, text: str = "") -> respx.Route:
    """Ответ без тела или с текстом — для 404/500."""
    return respx.get(url).mock(return_value=httpx.Response(status, text=text))


def mock_get_raw(url: str, text: str, status: int = 200) -> respx.Route:
    """Ответ с невалидным JSON — для проверки парсинга."""
    return respx.get(url).mock(
        return_value=httpx.Response(
            status, text=text, headers={"content-type": "application/json"}
        )
    )
