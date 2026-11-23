from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient

from aegis.main import app


TEST_GATEWAY = "a" * 64




VALID_REQUEST = {
    "prompt_id": "general_knowledge",
    "approved": True,
}


@pytest.fixture
def client(authenticated_environment, gateway_environment):

    return authenticated_environment[0]


@pytest.fixture(autouse=True)
def gateway_environment(monkeypatch, tmp_path):

    from aegis.security.access import limiter
    from aegis.storage.migrations import initialize_database

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "usage.sqlite3"

    initialize_database(path)

    from aegis.security.runtime_controls import runtime_controls
    from aegis.storage.settings import ApplicationSettings, save_settings

    save_settings(
        ApplicationSettings(cloud_enabled=True),
        1,
        path,
    )

    monkeypatch.setattr(runtime_controls, "path", path)
    monkeypatch.setattr(limiter, "path", path)

    monkeypatch.setenv(
        "AEGIS_GATEWAY_TOKEN", TEST_GATEWAY
    )

    monkeypatch.setenv(
        "GEMINI_MODEL", "gemini-3.1-flash-lite"
    )


def test_inference_disabled(monkeypatch, client):

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
def test_invalid_inference_requests(payload, client):

    response = client.post(
        "/api/v1/inference",
        json=payload,
    )

    assert response.status_code == 422


def test_emergency_stop(monkeypatch, client):

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


def test_inference_success(monkeypatch, client):

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


def test_direct_browser_blocked(client):

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


def test_wrong_gateway_credential(client):

    response = client.post(
        "/api/v1/inference",
        json=VALID_REQUEST,
        headers={"x-aegis-gateway-token": "invalid"},
    )

    assert response.status_code == 403


def test_rate_limit(tmp_path):

    from aegis.security.rate_limit import (
        PersistentRateLimiter,
        RateLimitExceeded,
    )
    from aegis.storage.migrations import initialize_database

    directory = tmp_path / "limiter"
    directory.mkdir(mode=0o700)

    path = directory / "usage.sqlite3"

    initialize_database(path)

    limiter = PersistentRateLimiter(path)

    for _ in range(3):
        limiter.acquire()

    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_unapproved_model(monkeypatch, client):

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
