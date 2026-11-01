"""Простая сессионная аутентификация для SQLAdmin.

Учётные данные берутся из настроек (env ``ADMIN__USERNAME`` / ``ADMIN__PASSWORD``,
по умолчанию ``admin`` / ``admin``). Сессия подписывается ``ADMIN__SECRET_KEY`` —
в продакшене обязательно переопределить.
"""

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse

from src.main.config.settings import settings


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        if username == settings.admin.USERNAME and password == settings.admin.PASSWORD:
            request.session["admin_authenticated"] = True
            return True
        return False

    async def logout(self, request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse(request.url_for("admin:login"), status_code=302)

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin_authenticated"))
