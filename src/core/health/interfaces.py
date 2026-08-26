from typing import Protocol

class HealthCheckerProtocol(Protocol):
    async def __call__(self) -> tuple[bool, str | None]: ...