from typing import Protocol


class GeneratorProtocol(Protocol):
    async def generate(
        self,
        prompt: list,
        think: bool = True,
        reasoning_effort: str | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Возвращает (title, description) на основе пожелания пользователя."""
        ...


class SceneGenerationLockProtocol(Protocol):
    """Блокировка генерации сцены (novel_id, scene_order).

    Реализация поверх Redis (SET NX + TTL): блокировка больше не привязана к
    транзакции Postgres, поэтому её нужно явно снимать через ``release``.
    """

    async def acquire(self, novel_id: int, scene_order: int) -> None:
        """Ждёт, пока другая генерация этой сцены завершится, и захватывает блокировку."""
        ...

    async def release(self, novel_id: int, scene_order: int) -> None:
        """Снимает блокировку, если её держит этот воркер."""
        ...

    async def is_locked(self, novel_id: int, scene_order: int) -> bool:
        """Идёт ли сейчас генерация этой сцены."""
        ...


class JobLockProtocol(Protocol):
    """Взаимоисключение генерации по ``job_id`` (Redis SET NX + TTL).

    Не является источником истины по результату: финальный статус хранится в
    Postgres (``generation_jobs``). TTL нужен, чтобы упавший воркер не оставил
    вечный лок — по истечении TTL блокировка освобождается сама.
    """

    async def acquire(self, job_id: int) -> bool:
        """Пытается захватить блокировку; ``False`` — её уже держит другой воркер."""
        ...

    async def release(self, job_id: int) -> None:
        """Снимает блокировку, если её держит этот воркер."""
        ...
