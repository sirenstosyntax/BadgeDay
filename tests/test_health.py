import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_liveness_only() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_each_dependency() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    configured = response.json()["configured"]
    assert set(configured) == {
        "anthropic",
        "azure_document_intelligence",
        "supabase",
        "stripe",
        "transcription",
    }
    assert isinstance(configured["transcription"], bool)
    dumped = json.dumps(response.json())
    assert "api_key" not in dumped
    assert "sk-" not in dumped
    assert "Token " not in dumped
