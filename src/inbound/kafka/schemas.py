from pydantic import BaseModel, Field


class SceneGenerateRequestedSchema(BaseModel):
    model_config = {"extra": "ignore"}

    job_id: int
    novel_id: int
    scene_order: int = Field(..., ge=0)


class NovelGenerateRequestedSchema(BaseModel):
    model_config = {"extra": "ignore"}

    job_id: int = Field(..., description="ID задачи")
    prompt: str = Field(..., min_length=1)
    universe_id: int | None = None
