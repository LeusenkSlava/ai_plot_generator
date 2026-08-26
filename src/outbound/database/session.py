from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.main.config.settings import settings

engine = create_async_engine(settings.postgres.dsn, echo=False, pool_pre_ping=True)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)