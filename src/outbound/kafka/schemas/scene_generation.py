from pydantic import BaseModel, Field


class SceneGenerateRequested(BaseModel):
    job_id: int
    novel_id: int
    # Шаг роадмапа и номер сцены внутри шага (с 1) — ключ идемпотентности.
    roadmap_id: int
    position: int = Field(ge=1)
