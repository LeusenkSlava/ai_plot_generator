class FakeSceneGenerationLock:
    """In-memory имитация advisory-блокировки по ключу (novel_id, scene_order)."""

    def __init__(self) -> None:
        self._locked: set[tuple[int, int]] = set()

    async def acquire(self, novel_id: int, scene_order: int) -> None:
        self._locked.add((novel_id, scene_order))

    async def is_locked(self, novel_id: int, scene_order: int) -> bool:
        return (novel_id, scene_order) in self._locked

    # ---------- удобства для тестов ----------

    def release(self, novel_id: int, scene_order: int) -> None:
        """Снять блокировку (в реальном репозитории это делает коммит/откат транзакции)."""
        self._locked.discard((novel_id, scene_order))
