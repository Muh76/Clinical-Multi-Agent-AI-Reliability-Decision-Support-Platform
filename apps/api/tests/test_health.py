from fastapi.testclient import TestClient

from clinical_ai_api.api.dependencies import get_health_service
from clinical_ai_api.main import create_app
from clinical_ai_api.schemas.base import ResponseMeta
from clinical_ai_api.schemas.health import DependencyHealth, HealthResponse


class FakeHealthService:
    async def get_health(self, *, request_id: str | None = None) -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="test-service",
            version="0.1.0",
            environment="test",
            services={"postgres": "connected", "redis": "connected"},
            checks={
                "postgres": DependencyHealth(status="connected"),
                "redis": DependencyHealth(status="connected"),
            },
            meta=ResponseMeta(request_id=request_id),
        )

    async def get_liveness(self, *, request_id: str | None = None) -> HealthResponse:
        return HealthResponse(
            status="healthy",
            service="test-service",
            version="0.1.0",
            environment="test",
            services={"application": "connected"},
            checks={"application": DependencyHealth(status="connected")},
            meta=ResponseMeta(request_id=request_id),
        )

    async def get_readiness(self, *, request_id: str | None = None) -> HealthResponse:
        return await self.get_health(request_id=request_id)


class FakeUnreadyHealthService(FakeHealthService):
    async def get_readiness(self, *, request_id: str | None = None) -> HealthResponse:
        return HealthResponse(
            status="unhealthy",
            service="test-service",
            version="0.1.0",
            environment="test",
            services={"postgres": "unavailable", "redis": "connected"},
            checks={
                "postgres": DependencyHealth(status="unavailable", detail="ConnectionError"),
                "redis": DependencyHealth(status="connected"),
            },
            meta=ResponseMeta(request_id=request_id),
        )


def test_health_endpoint() -> None:
    app = create_app()
    app.dependency_overrides[get_health_service] = lambda: FakeHealthService()
    client = TestClient(app)
    response = client.get(
        "/health",
        headers={
            "x-request-id": "test-request-id",
            "x-correlation-id": "test-correlation-id",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["meta"]["request_id"] == "test-request-id"
    assert response.json()["services"]["postgres"] == "connected"
    assert response.json()["checks"]["redis"]["status"] == "connected"
    assert response.headers["x-request-id"] == "test-request-id"
    assert response.headers["x-correlation-id"] == "test-correlation-id"


def test_liveness_endpoint() -> None:
    app = create_app()
    app.dependency_overrides[get_health_service] = lambda: FakeHealthService()
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["services"]["application"] == "connected"


def test_readiness_endpoint() -> None:
    app = create_app()
    app.dependency_overrides[get_health_service] = lambda: FakeHealthService()
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["services"]["postgres"] == "connected"


def test_readiness_endpoint_returns_503_when_unhealthy() -> None:
    app = create_app()
    app.dependency_overrides[get_health_service] = lambda: FakeUnreadyHealthService()
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
    assert response.json()["services"]["postgres"] == "unavailable"


def test_api_v1_patients_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/patients")
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["total"] == 0


def test_api_v1_safety_endpoint() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/safety/assess",
        json={"case_id": "case-1", "content": "candidate recommendation"},
    )
    assert response.status_code == 202
    assert response.json()["data"]["status"] == "queued"
    assert response.json()["data"]["requires_human_review"] is True


def test_api_v1_evaluation_endpoint() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/evaluation/runs",
        json={"case_id": "case-1", "evaluator_name": "grounding-check"},
    )
    assert response.status_code == 202
    assert response.json()["data"]["status"] == "queued"


def test_api_v1_evidence_workflow_endpoint() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/workflows/evidence-grounding",
        json={
            "case_id": "case-1",
            "patient_context": {
                "patient_id": "patient-1",
                "vitals": [
                    {
                        "name": "heart_rate",
                        "value": {"value": 112, "unit": "beats/min"},
                        "temporal": {"observed_at": "2026-05-20T08:00:00Z"},
                    }
                ],
                "labs": [
                    {
                        "test_name": "creatinine",
                        "value": {"value": 1.8, "unit": "mg/dL"},
                        "temporal": {"observed_at": "2026-05-20T08:10:00Z"},
                    }
                ],
                "medications": [
                    {
                        "medication_name": "vancomycin",
                        "route": "IV",
                        "temporal": {"observed_at": "2026-05-20T08:15:00Z"},
                    }
                ],
            },
            "evidence_query": "creatinine vancomycin renal dosing",
            "evidence_corpus": [
                {
                    "source_id": "local-renal-dosing",
                    "source_type": "local_policy",
                    "title": "Renal dosing policy",
                    "text": (
                        "Vancomycin dosing should consider renal function "
                        "and creatinine trends."
                    ),
                    "citation_id": "local_policy:local-renal-dosing",
                    "evidence_level": "guideline",
                },
                {
                    "source_id": "unrelated",
                    "source_type": "synthetic_protocol",
                    "title": "Unrelated protocol",
                    "text": "This protocol discusses discharge paperwork only.",
                },
            ],
            "top_k": 1,
        },
    )
    payload = response.json()["data"]
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["case_id"] == "case-1"
    assert payload["patient_id"] == "patient-1"
    assert payload["evidence"][0]["source_id"] == "local-renal-dosing"
    assert payload["citations"][0]["citation_id"] == "local_policy:local-renal-dosing"
    assert payload["retrieval_metadata"]["reranked"] is True
    assert payload["trace"]["workflow_id"] == payload["workflow_id"]
    assert len(payload["trace"]["steps"]) >= 5
