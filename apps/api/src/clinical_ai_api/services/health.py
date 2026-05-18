from clinical_ai_api.schemas.base import ResponseMeta
from clinical_ai_api.schemas.health import HealthResponse
from clinical_ai_platform.core.config import Settings


class HealthService:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    async def get_health(self, *, request_id: str | None = None) -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=self._settings.app_name,
            version=self._settings.app_version,
            environment=self._settings.environment,
            meta=ResponseMeta(request_id=request_id),
        )

