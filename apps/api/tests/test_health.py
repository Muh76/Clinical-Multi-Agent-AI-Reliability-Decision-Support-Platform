from fastapi.testclient import TestClient

from clinical_ai_api.main import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["meta"]["request_id"] is not None


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
