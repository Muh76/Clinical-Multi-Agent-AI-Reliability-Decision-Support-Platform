from clinical_ai_api.schemas.base import ResponseMeta
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    meta: ResponseMeta

