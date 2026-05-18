from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from clinical_ai_api.schemas.base import ResponseMeta

HealthStatus = Literal["healthy", "degraded", "unhealthy"]
DependencyStatus = Literal["connected", "degraded", "unavailable", "skipped"]


class DependencyHealth(BaseModel):
    status: DependencyStatus
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: HealthStatus
    service: str
    version: str
    environment: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    services: dict[str, DependencyStatus]
    checks: dict[str, DependencyHealth]
    meta: ResponseMeta
