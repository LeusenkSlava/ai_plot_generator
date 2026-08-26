from typing import Literal

from pydantic import BaseModel


class ComponentStatus(BaseModel):
    status: Literal["ok", "error"]
    details: str | None = None

class ComponentsHealth(BaseModel):
    postgres: ComponentStatus

class HealthResponse(BaseModel):
    status: Literal["ok", "unhealthy"]
    components: ComponentsHealth
