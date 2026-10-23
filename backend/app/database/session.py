from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import PoolProxiedConnection

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug and settings.environment == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)


@event.listens_for(engine.sync_engine, "connect")
def _force_utc_session_timezone(dbapi_connection: PoolProxiedConnection, connection_record) -> None:
    # The Postgres server/OS timezone (e.g. Asia/Kolkata here) otherwise leaks
    # into every session: date_trunc() and similar functions convert
    # timestamptz values into that zone before truncating, which silently
    # shifts aggregates like "group by month" near zone/month boundaries.
    # Storage stays UTC (per spec); only the session's working timezone
    # changes, so server-side date math matches the UTC values we store.
    dbapi_connection.run_async(lambda connection: connection.execute("SET TIME ZONE 'UTC'"))

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
