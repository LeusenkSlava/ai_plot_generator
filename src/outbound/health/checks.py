from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_postgres(session: AsyncSession) -> tuple[bool, str | None]:
    try:
        await session.execute(text("SELECT 1"))
        return True, None
    except Exception as e:
        return False, str(e)
