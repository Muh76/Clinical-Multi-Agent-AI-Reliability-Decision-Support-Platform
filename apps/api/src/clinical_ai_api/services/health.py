import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from clinical_ai_api.schemas.base import ResponseMeta
from clinical_ai_api.schemas.health import DependencyHealth, DependencyStatus, HealthResponse, HealthStatus
from clinical_ai_platform.core.config import Settings

CHECK_TIMEOUT_SECONDS = 2.0


class HealthService:
    def __init__(self, *, settings: Settings, engine: AsyncEngine, redis: Redis) -> None:
        self._settings = settings
        self._engine = engine
        self._redis = redis

    async def get_health(self, *, request_id: str | None = None) -> HealthResponse:
        checks = await self._run_dependency_checks()
        return self._build_response(
            status=self._aggregate_status(checks),
            checks=checks,
            request_id=request_id,
        )

    async def get_liveness(self, *, request_id: str | None = None) -> HealthResponse:
        checks = {
            "application": DependencyHealth(
                status="connected",
                detail="Application process is running.",
            )
        }
        return self._build_response(status="healthy", checks=checks, request_id=request_id)

    async def get_readiness(self, *, request_id: str | None = None) -> HealthResponse:
        checks = await self._run_dependency_checks()
        return self._build_response(
            status=self._readiness_status(checks),
            checks=checks,
            request_id=request_id,
        )

    async def _run_dependency_checks(self) -> dict[str, DependencyHealth]:
        postgres, redis = await asyncio.gather(
            self._timed_check("postgres", self._check_postgres),
            self._timed_check("redis", self._check_redis),
        )
        return {"postgres": postgres, "redis": redis}

    async def _timed_check(
        self,
        name: str,
        check: Callable[[], Awaitable[DependencyStatus]],
    ) -> DependencyHealth:
        start = perf_counter()
        try:
            result = await asyncio.wait_for(check(), timeout=CHECK_TIMEOUT_SECONDS)
        except TimeoutError:
            return DependencyHealth(
                status="unavailable",
                detail=f"{name} health check timed out.",
                latency_ms=round((perf_counter() - start) * 1000, 2),
            )
        except Exception as exc:
            return DependencyHealth(
                status="unavailable",
                detail=exc.__class__.__name__,
                latency_ms=round((perf_counter() - start) * 1000, 2),
            )
        return DependencyHealth(
            status=result,
            latency_ms=round((perf_counter() - start) * 1000, 2),
        )

    async def _check_postgres(self) -> DependencyStatus:
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return "connected"

    async def _check_redis(self) -> DependencyStatus:
        await self._redis.ping()
        return "connected"

    def _build_response(
        self,
        *,
        status: HealthStatus,
        checks: dict[str, DependencyHealth],
        request_id: str | None,
    ) -> HealthResponse:
        return HealthResponse(
            status=status,
            service=self._settings.app.name,
            version=self._settings.app.version,
            environment=str(self._settings.app.environment),
            timestamp=datetime.now(UTC),
            services={name: check.status for name, check in checks.items()},
            checks=checks,
            meta=ResponseMeta(request_id=request_id),
        )

    def _aggregate_status(self, checks: dict[str, DependencyHealth]) -> HealthStatus:
        statuses = {check.status for check in checks.values()}
        if statuses <= {"connected", "skipped"}:
            return "healthy"
        if "connected" in statuses:
            return "degraded"
        return "unhealthy"

    def _readiness_status(self, checks: dict[str, DependencyHealth]) -> HealthStatus:
        if all(check.status == "connected" for check in checks.values()):
            return "healthy"
        return "unhealthy"
