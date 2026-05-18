from clinical_ai_api.schemas.base import ResponseMeta
from pydantic import BaseModel


class DependencyHealth(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    dependencies: dict[str, DependencyHealth]
    meta: ResponseMeta
