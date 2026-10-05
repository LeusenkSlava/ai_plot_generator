from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.generation_jobs.models import GenerationJobStatus
from src.outbound.database.models.base_model import BaseModel
from src.outbound.database.utils import pg_enum


class GenerationJobModel(BaseModel):
    """Задача генерации для идемпотентной обработки по job_id."""

    __tablename__ = "generation_jobs"

    job_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    status: Mapped[GenerationJobStatus] = mapped_column(
        pg_enum(GenerationJobStatus, native=False),
        nullable=True,
    )
    result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
