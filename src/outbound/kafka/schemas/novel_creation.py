from typing import Literal

from pydantic import BaseModel


class NovelGenerateRequested(BaseModel):
    job_id: int
    prompt: str
    universe_id: int | None = None


class GenerationResult(BaseModel):
    job_id: int
    status: Literal["done", "failed"]
    result_id: int | None = None
    error: str | None = None
