from redis.asyncio import ConnectionPool, Redis

from clinical_ai_platform.core.config import Settings, get_settings


class RedisManager:
    """Lifecycle manager for a shared async Redis client."""

    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

    def init(self, settings: Settings | None = None) -> None:
        if self._client is not None:
            return

        resolved_settings = settings or get_settings()
        self._pool = ConnectionPool.from_url(
            str(resolved_settings.redis.url),
            max_connections=resolved_settings.redis.max_connections,
            socket_timeout=resolved_settings.redis.socket_timeout,
            socket_connect_timeout=resolved_settings.redis.socket_connect_timeout,
            health_check_interval=resolved_settings.redis.health_check_interval,
            decode_responses=True,
        )
        self._client = Redis(connection_pool=self._pool)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        if self._pool is not None:
            await self._pool.aclose()
        self._client = None
        self._pool = None

    def client(self) -> Redis:
        if self._client is None:
            self.init()
        if self._client is None:
            raise RuntimeError("Redis client has not been initialized.")
        return self._client

    async def ping(self) -> bool:
        return bool(await self.client().ping())


redis_manager = RedisManager()


def init_redis(settings: Settings | None = None) -> None:
    redis_manager.init(settings)


async def close_redis() -> None:
    await redis_manager.close()


def get_redis() -> Redis:
    return redis_manager.client()


async def ping_redis() -> bool:
    return await redis_manager.ping()
