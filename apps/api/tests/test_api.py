from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_healthcheck():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True


def test_list_leagues():
    response = client.get("/api/leagues")
    assert response.status_code == 200
    leagues = response.json()
    assert any(item["key"] == "premier-league" for item in leagues)
