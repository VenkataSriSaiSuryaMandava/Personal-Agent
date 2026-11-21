import pytest

from fastapi.testclient import TestClient
from aegis.main import app


client = TestClient(app)


def test_status():
    response = client.get("/api/v1/status")

    assert response.status_code == 200
    assert response.json()["cloud_requests_enabled"] is False
    assert response.json()["execution_enabled"] is False


def test_preview():
    response = client.post(
        "/api/v1/chat",
        json={"message": "Example prompt"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "preview"
    assert response.json()["transmitted"] is False
    assert response.json()["executed"] is False
    assert "Example prompt" not in response.text


@pytest.mark.parametrize("payload", [
    {},
    {"message": ""},
    {"message": "   "},
    {"message": "x" * 4001},
    {"message": 123},
    {"message": "sample", "scoped_grant": True},
])
def test_invalid_requests(payload):
    response = client.post(
        "/api/v1/chat",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid request"
    }


def test_untrusted_host():
    response = client.get(
        "/health",
        headers={"host": "example.com"},
    )

    assert response.status_code == 400
