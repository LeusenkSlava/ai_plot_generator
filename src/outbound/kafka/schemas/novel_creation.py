from typing import Literal

from pydantic import BaseModel


class GenerationResult(BaseModel):
    job_id: int
    status: Literal["done", "failed"]
    result_id: int | None = None
    error: str | None = None
