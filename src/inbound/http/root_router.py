from fastapi import APIRouter
from starlette.responses import RedirectResponse

from src.inbound.http.health.router import router as health_router
from src.inbound.http.novels.router import router as novels_router


def make_fastapi_root_router(*, debug_mode: bool) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/",
        include_in_schema=False,
    )
    async def redirect_to_docs() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    router.include_router(health_router)
    router.include_router(novels_router)

    return router
