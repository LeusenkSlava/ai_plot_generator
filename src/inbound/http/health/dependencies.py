# inbound/http/health/dependencies.py
from functools import partial
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.health.services import HealthService
from src.outbound.database.dependencies import get_db_session
from src.outbound.health.checks import check_postgres


def get_health_service() -> HealthService:
    return HealthService()


def get_health_checkers(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    return {
        "postgres": partial(check_postgres, session),
    }
