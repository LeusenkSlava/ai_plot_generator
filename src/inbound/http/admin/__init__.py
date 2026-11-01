"""Встроенная админка (SQLAdmin): промпты и тест промпта диалога."""

from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin

from src.inbound.http.admin.auth import AdminAuth
from src.inbound.http.admin.dialogue_test import DialogueTestAdmin
from src.inbound.http.admin.prompt_admin import PromptAdmin
from src.main.config.settings import settings
from src.outbound.database.session import engine

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def setup_admin(app: FastAPI) -> None:
    """Подключает SQLAdmin к FastAPI-приложению (таблица ``prompts`` + тест диалога)."""
    if not settings.admin.ENABLED:
        return

    admin = Admin(
        app,
        engine,
        base_url=settings.admin.BASE_URL,
        title=settings.admin.TITLE,
        templates_dir=str(PROJECT_ROOT / "templates"),
        authentication_backend=AdminAuth(secret_key=settings.admin.SECRET_KEY),
    )
    admin.add_view(PromptAdmin)
    admin.add_view(DialogueTestAdmin)
