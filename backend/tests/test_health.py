from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "voice_provider" in body


def test_root_ok():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "cimet-energy-voice-agent"
