from sqladmin import ModelView
from sqlalchemy import func, select, update
from starlette.requests import Request
from wtforms import SelectField, TextAreaField

from src.core.novels.models import PromptKey, PromptVariant
from src.outbound.database.models.prompts import PromptModel


class PromptAdmin(ModelView, model=PromptModel):
    name = "Промпт"
    name_plural = "Промпты"
    icon = "fa-solid fa-scroll"

    column_list = [
        PromptModel.id,
        PromptModel.key,
        PromptModel.variant,
        PromptModel.version,
        PromptModel.is_active,
        PromptModel.system_template,
        PromptModel.user_template,
        PromptModel.created_at,
        PromptModel.updated_at,
    ]
    column_searchable_list = [PromptModel.key, PromptModel.variant]
    column_sortable_list = [
        PromptModel.id,
        PromptModel.key,
        PromptModel.variant,
        PromptModel.version,
        PromptModel.is_active,
        PromptModel.created_at,
        PromptModel.updated_at,
    ]
    column_default_sort = [
        (PromptModel.key, False),
        (PromptModel.variant, False),
        (PromptModel.version, True),
    ]
    column_labels = {
        "id": "ID",
        "key": "Ключ",
        "variant": "Вариант",
        "version": "Версия",
        "is_active": "Активна",
        "system_template": "System-шаблон",
        "user_template": "User-шаблон",
        "created_at": "Создана",
        "updated_at": "Обновлена",
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    # ``version`` намеренно отсутствует в форме — проставляется автоматически.
    form_columns = [
        PromptModel.key,
        PromptModel.variant,
        PromptModel.system_template,
        PromptModel.user_template,
        PromptModel.is_active,
    ]
    form_overrides = {
        "key": SelectField,
        "variant": SelectField,
        "system_template": TextAreaField,
        "user_template": TextAreaField,
    }
    form_args = {
        "key": {"choices": [(k.value, k.value) for k in PromptKey]},
        "variant": {"choices": [(v.value, v.value) for v in PromptVariant]},
        "system_template": {"render_kw": {"rows": 22}},
        "user_template": {"render_kw": {"rows": 12}},
    }

    async def _create_version(
        self,
        session,
        *,
        key: str,
        variant: str,
        system_template: str,
        user_template: str,
        is_active: bool,
    ) -> PromptModel:
        """Добавляет новую append-only версию и гасит активную версию той же пары.

        Не коммитит и не делает ``refresh`` — это делает вызывающий, чтобы и
        ``insert_model``, и ``update_model`` завершали транзакцию одинаково.
        """
        max_version = (
            await session.execute(
                select(func.max(PromptModel.version)).where(
                    PromptModel.key == key,
                    PromptModel.variant == variant,
                )
            )
        ).scalar_one()
        version = (max_version or 0) + 1

        if is_active:
            await session.execute(
                update(PromptModel)
                .where(
                    PromptModel.key == key,
                    PromptModel.variant == variant,
                    PromptModel.is_active.is_(True),
                )
                .values(is_active=False)
            )

        obj = PromptModel(
            key=key,
            variant=variant,
            version=version,
            system_template=system_template,
            user_template=user_template,
            is_active=is_active,
        )
        session.add(obj)
        return obj

    async def insert_model(self, request: Request, data: dict) -> PromptModel:
        async with self.session_maker() as session:
            obj = await self._create_version(
                session,
                key=data.get("key") or "",
                variant=data.get("variant") or "",
                system_template=data.get("system_template") or "",
                user_template=data.get("user_template") or "",
                is_active=bool(data.get("is_active")),
            )
            await session.commit()
            await session.refresh(obj)
            return obj

    async def update_model(self, request: Request, pk: str, data: dict) -> PromptModel:
        async with self.session_maker() as session:
            obj = (
                await session.execute(
                    select(PromptModel).where(PromptModel.id == int(pk))
                )
            ).scalar_one()

            new_key = data.get("key", obj.key)
            new_variant = data.get("variant", obj.variant)
            new_system = data.get("system_template", obj.system_template)
            new_user = data.get("user_template", obj.user_template)
            new_is_active = bool(data.get("is_active"))

            content_changed = (
                new_key != obj.key
                or new_variant != obj.variant
                or new_system != obj.system_template
                or new_user != obj.user_template
            )

            if not content_changed:
                # Меняется только признак активности — in-place правка допустима:
                # текст/версия не трогаются, append-only инвариант не нарушается.
                if new_is_active:
                    await session.execute(
                        update(PromptModel)
                        .where(
                            PromptModel.key == new_key,
                            PromptModel.variant == new_variant,
                            PromptModel.is_active.is_(True),
                            PromptModel.id != obj.id,
                        )
                        .values(is_active=False)
                    )
                obj.is_active = new_is_active
                await session.commit()
                await session.refresh(obj)
                return obj

            # Контент изменился → append-only: новая версия (как при создании).
            # Прежняя активная версия той же пары гасится внутри ``_create_version``.
            obj = await self._create_version(
                session,
                key=new_key,
                variant=new_variant,
                system_template=new_system,
                user_template=new_user,
                is_active=new_is_active,
            )
            await session.commit()
            await session.refresh(obj)
            return obj
