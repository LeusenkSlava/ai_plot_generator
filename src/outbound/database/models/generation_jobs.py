from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.outbound.database.models.base_model import BaseModel


class GenerationJobModel(BaseModel):
    """Результат задачи генерации из my_choice_api — для идемпотентной обработки по job_id."""

    __tablename__ = "generation_jobs"

    job_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
