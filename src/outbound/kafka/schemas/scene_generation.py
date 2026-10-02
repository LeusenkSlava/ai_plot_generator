from pydantic import BaseModel, Field


class SceneGenerateRequested(BaseModel):
    job_id: int
    novel_id: int
    # Сквозной порядковый номер сцены в новелле, с 1
    scene_order: int = Field(ge=1)
