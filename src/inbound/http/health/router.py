from fastapi import APIRouter

from src.inbound.http.health.checks import router as checks_router

router = APIRouter()

router.include_router(checks_router, tags=["checks"])
