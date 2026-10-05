from typing import Protocol


class GeneratorProtocol(Protocol):
    async def generate(self, prompt: list) -> dict:
        """Возвращает (title, description) на основе пожелания пользователя."""
        ...


class SceneGenerationLockProtocol(Protocol):
    """Блокировка генерации сцены (novel_id, scene_order) на время транзакции."""

    async def acquire(self, novel_id: int, scene_order: int) -> None:
        """Ждёт, пока другая генерация этой сцены завершится, и захватывает блокировку."""
        ...

    async def is_locked(self, novel_id: int, scene_order: int) -> bool:
        """Идёт ли сейчас генерация этой сцены."""
        ...
