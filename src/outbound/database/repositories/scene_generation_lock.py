from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SceneGenerationLock:
    """Advisory-блокировка Postgres по ключу (roadmap_id, position).

    ``roadmap_id`` — суррогатный PK шага роадмапа (глобально уникален), поэтому
    ``novel_id`` в ключе не нужен. Блокировка держится до конца транзакции и
    снимается при коммите/откате или обрыве соединения, поэтому упавший воркер
    не оставляет «вечную» блокировку.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def acquire(self, novel_id: int, roadmap_id: int, position: int) -> None:
        await self._session.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "CAST(:roadmap_id AS integer), CAST(:position AS integer))"
            ),
            {"roadmap_id": roadmap_id, "position": position},
        )

    async def is_locked(self, novel_id: int, roadmap_id: int, position: int) -> bool:
        # Ключ из двух int4 хранится в pg_locks как classid/objid с objsubid = 2
        result = await self._session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                "AND classid::bigint = :roadmap_id AND objid::bigint = :position "
                "AND objsubid = 2 AND granted)"
            ),
            {"roadmap_id": roadmap_id, "position": position},
        )
        return bool(result.scalar_one())
