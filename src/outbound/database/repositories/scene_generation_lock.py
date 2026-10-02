from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SceneGenerationLock:
    """Advisory-блокировка Postgres по ключу (novel_id, scene_order).

    Держится до конца транзакции и снимается при коммите/откате или обрыве соединения,
    поэтому упавший воркер не оставляет «вечную» блокировку.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def acquire(self, novel_id: int, scene_order: int) -> None:
        await self._session.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "CAST(:novel_id AS integer), CAST(:scene_order AS integer))"
            ),
            {"novel_id": novel_id, "scene_order": scene_order},
        )

    async def is_locked(self, novel_id: int, scene_order: int) -> bool:
        # Ключ из двух int4 хранится в pg_locks как classid/objid с objsubid = 2
        result = await self._session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                "AND classid::bigint = :novel_id AND objid::bigint = :scene_order "
                "AND objsubid = 2 AND granted)"
            ),
            {"novel_id": novel_id, "scene_order": scene_order},
        )
        return bool(result.scalar_one())
