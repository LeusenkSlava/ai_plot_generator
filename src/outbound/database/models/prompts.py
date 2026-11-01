from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from src.outbound.database.models.base_model import BaseModel


class PromptModel(BaseModel):
    """Версия шаблона промпта (append-only версионирование по (key, variant, version))."""

    __tablename__ = "prompts"
    __table_args__ = (
        UniqueConstraint("key", "variant", "version", name="uq_prompts_key_variant_version"),
    )

    key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    variant: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_template: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    def __repr__(self):
        return (
            f"<PromptModel(id={self.id}, key={self.key!r}, variant={self.variant!r}, "
            f"version={self.version}, is_active={self.is_active})>"
        )
