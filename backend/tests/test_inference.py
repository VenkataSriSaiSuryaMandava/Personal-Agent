from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient

from aegis.main import app


TEST_GATEWAY = "a" * 64

client = TestClient(
    app,
    headers={"x-aegis-gateway-token": TEST_GATEWAY},
)


@pytest.fixture(autouse=True)
def gateway_environment(monkeypatch):

    from aegis.security.access import limiter

    monkeypatch.setenv(
        "AEGIS_GATEWAY_TOKEN", TEST_GATEWAY
    )

    monkeypatch.setenv(
        "GEMINI_MODEL", "gemini-3.1-flash-lite"
    )

    limiter._requests.clear()

    yield

    limiter._requests.clear()

VALID_REQUEST = {
    "prompt_id": "general_knowledge",
    "approved": True,
}


def test_inference_disabled(monkeypatch):

    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "0")

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        response = client.post(
            "/api/v1/inference",
            json=VALID_REQUEST,
        )

        assert response.status_code == 403
        provider.assert_not_called()


@pytest.mark.parametrize("payload", [
    {"prompt_id": "general_knowledge"},
    {"prompt_id": "general_knowledge", "approved": False},
    {"prompt_id": "private_message", "approved": True},
    {
        "prompt_id": "general_knowledge",
        "approved": True,
        "message": "Private information",
    },
])
def test_invalid_inference_requests(payload):

    response = client.post(
        "/api/v1/inference",
        json=payload,
    )

    assert response.status_code == 422


def test_emergency_stop(monkeypatch):

    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")
    monkeypatch.setenv("AEGIS_EMERGENCY_STOP", "1")

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        response = client.post(
            "/api/v1/inference",
            json=VALID_REQUEST,
        )

        assert response.status_code == 403
        provider.assert_not_called()


def test_inference_success(monkeypatch):

    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")
    monkeypatch.setenv("AEGIS_EMERGENCY_STOP", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        provider.return_value.complete.return_value = (
            "Synthetic model response"
        )

        response = client.post(
            "/api/v1/inference",
            json=VALID_REQUEST,
        )

        assert response.status_code == 200
        assert response.json()["message"] == (
            "Synthetic model response"
        )
        assert response.json()["executed"] is False

        provider.return_value.complete.assert_called_once_with(
            "Explain how a binary search algorithm works."
        )


def test_direct_browser_blocked():

    response = client.post(
        "/api/v1/inference",
        json=VALID_REQUEST,
        headers={"origin": "https://example.com"},
    )

    assert response.status_code == 403


def test_missing_gateway_credential():

    anonymous = TestClient(app)

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        response = anonymous.post(
            "/api/v1/inference",
            json=VALID_REQUEST,
        )

        assert response.status_code == 403
        provider.assert_not_called()


def test_wrong_gateway_credential():

    response = client.post(
        "/api/v1/inference",
        json=VALID_REQUEST,
        headers={"x-aegis-gateway-token": "invalid"},
    )

    assert response.status_code == 403


def test_rate_limit():

    from aegis.security.access import InferenceLimiter
    from fastapi import HTTPException

    limiter = InferenceLimiter()

    for _ in range(3):
        limiter.acquire()

    with pytest.raises(HTTPException) as error:
        limiter.acquire()

    assert error.value.status_code == 429


def test_unapproved_model(monkeypatch):

    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")
    monkeypatch.setenv("AEGIS_EMERGENCY_STOP", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-other")

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        response = client.post(
            "/api/v1/inference",
            json=VALID_REQUEST,
        )

        assert response.status_code == 403
        provider.assert_not_called()
