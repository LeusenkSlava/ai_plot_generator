from typing import Annotated

from fastapi import APIRouter, Depends

from src.core.health.services import HealthService
from src.inbound.http.health.dependencies import get_health_checkers, get_health_service
from src.inbound.http.health.schemas import (
    ComponentsHealth,
    ComponentStatus,
    HealthResponse,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    health_service: Annotated[HealthService, Depends(get_health_service)],
    checkers: Annotated[dict, Depends(get_health_checkers)],
):
    result = await health_service.check(checkers)

    components_by_name = {c.name: c for c in result.components}
    return HealthResponse(
        status="ok" if result.healthy else "unhealthy",
        components=ComponentsHealth(
            postgres=ComponentStatus(
                status="ok" if components_by_name["postgres"].ok else "error",
                details=components_by_name["postgres"].details,
            )
        ),
    )
