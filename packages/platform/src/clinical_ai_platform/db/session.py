from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from clinical_ai_platform.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    resolved_settings = settings or get_settings()
    return create_async_engine(
        str(resolved_settings.database_url),
        pool_pre_ping=True,
        pool_size=resolved_settings.database_pool_size,
        max_overflow=resolved_settings.database_max_overflow,
        pool_timeout=resolved_settings.database_pool_timeout,
        pool_recycle=resolved_settings.database_pool_recycle,
        echo=resolved_settings.database_echo,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


def init_database(settings: Settings | None = None) -> None:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(settings)
        _session_factory = create_session_factory(_engine)


async def close_database() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    if _engine is None:
        init_database()
    if _engine is None:
        raise RuntimeError("Database engine has not been initialized.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        init_database()
    if _session_factory is None:
        raise RuntimeError("Database session factory has not been initialized.")
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
