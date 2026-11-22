import pytest

from unittest.mock import patch

from fastapi.testclient import TestClient

from aegis.main import app

from aegis.security.sessions import IDLE_TIMEOUT

from aegis.security.owner import reset_owner_password

from aegis.security.passwords import (
    hash_password,
    verify_password,
    InvalidPassword,
)


GATEWAY = "a" * 64

ENDPOINTS = [
    (
        "GET",
        "/api/v1/status",
        None,
    ),
    (
        "POST",
        "/api/v1/chat",
        {"message": "Synthetic prompt"},
    ),
    (
        "POST",
        "/api/v1/inference",
        {
            "prompt_id": "general_knowledge",
            "approved": True,
        },
    ),
]


def send(client, method, path, payload=None, **kwargs):

    if payload is not None:

        kwargs["json"] = payload

    return client.request(
        method,
        path,
        **kwargs,
    )


@pytest.mark.parametrize(
    "method,path,payload",
    ENDPOINTS,
)
def test_anonymous_requests_denied(
    authenticated_environment,
    method,
    path,
    payload,
):

    with TestClient(app) as client:

        response = send(
            client,
            method,
            path,
            payload,
        )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "method,path,payload",
    ENDPOINTS,
)
def test_gateway_alone_insufficient(
    authenticated_environment,
    method,
    path,
    payload,
):

    with TestClient(
        app,
        headers={
            "x-aegis-gateway-token": GATEWAY,
        },
    ) as client:

        response = send(
            client,
            method,
            path,
            payload,
        )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path,payload",
    ENDPOINTS,
)
def test_session_without_gateway_denied(
    authenticated_environment,
    method,
    path,
    payload,
):

    _, _, token, _, _ = authenticated_environment

    with TestClient(
        app,
        headers={
            "Authorization": f"Bearer {token}",
        },
    ) as client:

        response = send(
            client,
            method,
            path,
            payload,
        )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "method,path,payload",
    ENDPOINTS,
)
def test_unknown_session_denied(
    authenticated_environment,
    method,
    path,
    payload,
):

    client, _, _, _, _ = authenticated_environment

    response = send(
        client,
        method,
        path,
        payload,
        headers={
            "Authorization": "Bearer " + "z" * 43,
        },
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path,payload",
    ENDPOINTS,
)
def test_expired_session_denied(
    authenticated_environment,
    method,
    path,
    payload,
):

    client, _, _, _, now = authenticated_environment

    now[0] += IDLE_TIMEOUT

    response = send(
        client,
        method,
        path,
        payload,
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path,payload",
    ENDPOINTS,
)
def test_revoked_session_denied(
    authenticated_environment,
    method,
    path,
    payload,
):

    client, service, token, _, _ = authenticated_environment

    service.logout(token)

    response = send(
        client,
        method,
        path,
        payload,
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path,payload",
    ENDPOINTS,
)
def test_browser_origin_denied(
    authenticated_environment,
    method,
    path,
    payload,
):

    client, _, _, _, _ = authenticated_environment

    response = send(
        client,
        method,
        path,
        payload,
        headers={
            "origin": "https://example.com",
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "method,path,payload",
    ENDPOINTS,
)
def test_insecure_database_denies_access(
    authenticated_environment,
    method,
    path,
    payload,
):

    client, _, _, database_path, _ = (
        authenticated_environment
    )

    database_path.chmod(0o644)

    response = send(
        client,
        method,
        path,
        payload,
    )

    assert response.status_code == 503


def test_authenticated_chat(
    authenticated_environment,
):

    client, _, _, _, _ = authenticated_environment

    response = client.post(
        "/api/v1/chat",
        json={"message": "Synthetic prompt"},
    )

    assert response.status_code == 200
    assert response.json()["transmitted"] is False


def test_authenticated_status(
    authenticated_environment,
):

    client, _, _, _, _ = authenticated_environment

    assert client.get(
        "/api/v1/status"
    ).status_code == 200


def test_password_recovery_invalidates_api_access(
    authenticated_environment,
):

    client, _, _, path, _ = authenticated_environment

    reset_owner_password(
        "Replacement synthetic password!",
        path,
    )

    assert client.get(
        "/api/v1/status"
    ).status_code == 401


def test_unauthorized_inference_never_calls_provider(
    authenticated_environment,
    monkeypatch,
):

    client, service, token, _, _ = (
        authenticated_environment
    )

    service.logout(token)

    monkeypatch.setenv(
        "AEGIS_CLOUD_ENABLED",
        "1",
    )

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        response = client.post(
            "/api/v1/inference",
            json={
                "prompt_id": "general_knowledge",
                "approved": True,
            },
        )

        assert response.status_code == 401

        provider.assert_not_called()


def test_health_remains_public():

    with TestClient(app) as client:

        assert client.get("/health").status_code == 200


def test_malformed_unicode_password_rejected():

    invalid = "Synthetic password " + chr(0xD800)

    with pytest.raises(InvalidPassword):

        hash_password(invalid)


def test_malformed_unicode_verification_rejected():

    encoded = hash_password(
        "Synthetic password for testing!"
    )

    assert verify_password(
        chr(0xD800),
        encoded,
    ) is False
