from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

# Фабрика границ транзакции. В продакшене это ``session.begin`` (commit/rollback
# на выходе из контекста); в тестах генераторов — ``noop_step``, поскольку фейки
# работают в памяти и не нуждаются в реальной транзакции.
TransactionFactory = Callable[[], AbstractAsyncContextManager[None]]


@asynccontextmanager
async def noop_step():
    """Пустая транзакционная граница для генераторов без реальной БД."""
    yield
