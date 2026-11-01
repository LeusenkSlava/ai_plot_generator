from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.novels.models import Prompt
from src.outbound.database.models.prompts import PromptModel


class PromptRepository:
    """Версионирование шаблонов промптов: append-only по (key, variant, version)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_active(self, key: str, variant: str) -> Prompt | None:
        result = await self._session.execute(
            select(PromptModel).where(
                PromptModel.key == key,
                PromptModel.variant == variant,
                PromptModel.is_active.is_(True),
            )
        )
        db_prompt = result.scalar_one_or_none()
        return self._to_domain(db_prompt) if db_prompt else None

    async def add(self, prompt: Prompt) -> Prompt:
        """Добавляет новую версию: гасит активную, version = max(version) + 1."""
        max_version = await self._session.execute(
            select(func.max(PromptModel.version)).where(
                PromptModel.key == prompt.key,
                PromptModel.variant == prompt.variant,
            )
        )
        next_version = (max_version.scalar_one() or 0) + 1

        await self._session.execute(
            update(PromptModel)
            .where(
                PromptModel.key == prompt.key,
                PromptModel.variant == prompt.variant,
                PromptModel.is_active.is_(True),
            )
            .values(is_active=False)
        )

        db_prompt = PromptModel(
            key=prompt.key,
            variant=prompt.variant,
            version=next_version,
            system_template=prompt.system_template,
            user_template=prompt.user_template,
            is_active=True,
        )
        self._session.add(db_prompt)
        await self._session.flush()
        return self._to_domain(db_prompt)

    async def list_versions(self, key: str, variant: str) -> list[Prompt]:
        result = await self._session.execute(
            select(PromptModel)
            .where(PromptModel.key == key, PromptModel.variant == variant)
            .order_by(PromptModel.version)
        )
        return [self._to_domain(p) for p in result.scalars().all()]

    @staticmethod
    def _to_domain(db_prompt: PromptModel) -> Prompt:
        return Prompt(
            id=db_prompt.id,
            created_at=db_prompt.created_at,
            updated_at=db_prompt.updated_at,
            key=db_prompt.key,
            variant=db_prompt.variant,
            version=db_prompt.version,
            system_template=db_prompt.system_template,
            user_template=db_prompt.user_template,
            is_active=db_prompt.is_active,
        )
