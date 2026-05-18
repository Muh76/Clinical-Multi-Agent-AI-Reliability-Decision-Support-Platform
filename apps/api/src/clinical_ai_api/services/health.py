from redis.asyncio import Redis

from clinical_ai_api.schemas.base import ResponseMeta
from clinical_ai_api.schemas.health import DependencyHealth, HealthResponse
from clinical_ai_platform.core.config import Settings


class HealthService:
    def __init__(self, *, settings: Settings, redis: Redis) -> None:
        self._settings = settings
        self._redis = redis

    async def get_health(self, *, request_id: str | None = None) -> HealthResponse:
        redis_health = await self._check_redis()
        return HealthResponse(
            status="ok",
            service=self._settings.app_name,
            version=self._settings.app_version,
            environment=self._settings.environment,
            dependencies={"redis": redis_health},
            meta=ResponseMeta(request_id=request_id),
        )

    async def _check_redis(self) -> DependencyHealth:
        try:
            await self._redis.ping()
        except Exception as exc:
            return DependencyHealth(status="unhealthy", detail=exc.__class__.__name__)
        return DependencyHealth(status="ok")
