from pydantic import BaseModel, Field

from src.core.novels.models import NovelMode


class SceneGenerateRequestedSchema(BaseModel):
    model_config = {"extra": "ignore"}

    job_id: int
    novel_id: int
    roadmap_id: int
    position: int = Field(..., ge=1)


class BranchGenerateRequestedSchema(BaseModel):
    model_config = {"extra": "ignore"}

    job_id: int
    novel_id: int
    roadmap_choice_id: int


class NovelGenerateRequestedSchema(BaseModel):
    model_config = {"extra": "ignore"}

    job_id: int = Field(..., description="ID задачи")
    prompt: str = Field(..., min_length=1)
    universe_id: int | None = None
    mode: NovelMode = NovelMode.LINEAR
