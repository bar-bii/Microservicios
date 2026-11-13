from fastapi.testclient import TestClient

from presentation.main import app

client = TestClient(app)


def test_health_returns_200_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}
