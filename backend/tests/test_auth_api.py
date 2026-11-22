import json

import pytest

from fastapi.testclient import TestClient

from aegis.main import app
from aegis.api import auth

from aegis.security.authentication import (
    AuthenticationService,
)

from aegis.security.owner import create_owner

from aegis.security.sessions import (
    hash_token,
    IDLE_TIMEOUT,
)

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


USERNAME = "test-owner"
PASSWORD = "Synthetic API password 2026!"
GATEWAY = "a" * 64

LOGIN = "/api/v1/auth/login"
SESSION = "/api/v1/auth/session"
LOGOUT = "/api/v1/auth/logout"


@pytest.fixture
def environment(tmp_path, monkeypatch):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "auth.sqlite3"

    initialize_database(path)

    create_owner(USERNAME, PASSWORD, path)

    now = [100000]

    service = AuthenticationService(
        path,
        clock=lambda: now[0],
    )

    monkeypatch.setattr(
        auth,
        "service",
        service,
    )

    monkeypatch.setenv(
        "AEGIS_GATEWAY_TOKEN",
        GATEWAY,
    )

    monkeypatch.setenv(
        "AEGIS_CLOUD_ENABLED",
        "0",
    )

    client = TestClient(
        app,
        headers={
            "x-aegis-gateway-token": GATEWAY,
        },
    )

    return client, path, now


def login(client):

    return client.post(
        LOGIN,
        json={
            "username": USERNAME,
            "password": PASSWORD,
        },
    )


def bearer(token):

    return {
        "Authorization": f"Bearer {token}",
    }


def test_successful_login(environment):

    client, _, _ = environment

    response = login(client)

    assert response.status_code == 200

    payload = response.json()

    assert payload["authenticated"] is True
    assert len(payload["session_token"]) == 43
    assert payload["expires_in"] == 43200


def test_password_not_returned(environment):

    client, _, _ = environment

    response = login(client)

    assert PASSWORD not in response.text


def test_authentication_response_not_cached(environment):

    client, _, _ = environment

    response = login(client)

    assert response.headers["cache-control"] == "no-store"


def test_session_token_stored_as_hash(environment):

    client, path, _ = environment

    token = login(client).json()["session_token"]

    with connect(path) as connection:

        row = connection.execute(
            "SELECT token_hash FROM auth_sessions"
        ).fetchone()

    assert row["token_hash"] == hash_token(token)
    assert row["token_hash"] != token


def test_invalid_credentials(environment):

    client, _, _ = environment

    response = client.post(
        LOGIN,
        json={
            "username": USERNAME,
            "password": "Incorrect password",
        },
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Invalid credentials",
    }


def test_unknown_owner_same_error(environment):

    client, _, _ = environment

    response = client.post(
        LOGIN,
        json={
            "username": "unknown-owner",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Invalid credentials",
    }


def test_missing_gateway(environment):

    response = TestClient(app).post(
        LOGIN,
        json={
            "username": USERNAME,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 403


def test_invalid_gateway(environment):

    response = TestClient(app).post(
        LOGIN,
        headers={
            "x-aegis-gateway-token": "b" * 64,
        },
        json={
            "username": USERNAME,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 403


def test_missing_gateway_configuration(
    environment,
    monkeypatch,
):

    client, _, _ = environment

    monkeypatch.delenv(
        "AEGIS_GATEWAY_TOKEN",
    )

    assert login(client).status_code == 403


@pytest.mark.parametrize(
    "origin",
    [
        "https://example.com",
        "http://localhost:3000",
        "null",
    ],
)
def test_direct_browser_request_denied(
    environment,
    origin,
):

    client, _, _ = environment

    response = client.post(
        LOGIN,
        headers={"origin": origin},
        json={
            "username": USERNAME,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 403


def test_extra_fields_rejected(environment):

    client, _, _ = environment

    response = client.post(
        LOGIN,
        json={
            "username": USERNAME,
            "password": PASSWORD,
            "is_admin": True,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"username": USERNAME},
        {"username": USERNAME, "password": None},
        {"username": 123, "password": PASSWORD},
        {"username": USERNAME, "password": "a" * 129},
    ],
)
def test_invalid_payload(environment, payload):

    client, _, _ = environment

    response = client.post(LOGIN, json=payload)

    assert response.status_code == 422


def test_malformed_json(environment):

    client, _, _ = environment

    response = client.post(
        LOGIN,
        content="{invalid",
        headers={
            "content-type": "application/json",
        },
    )

    assert response.status_code == 422


def test_incorrect_content_type(environment):

    client, _, _ = environment

    response = client.post(
        LOGIN,
        content="invalid",
        headers={
            "content-type": "text/plain",
        },
    )

    assert response.status_code == 415


def test_oversized_body(environment):

    client, _, _ = environment

    response = client.post(
        LOGIN,
        content=json.dumps({
            "username": "a" * 5000,
            "password": PASSWORD,
        }),
        headers={
            "content-type": "application/json",
        },
    )

    assert response.status_code == 413


def test_validate_session(environment):

    client, _, _ = environment

    token = login(client).json()["session_token"]

    response = client.get(
        SESSION,
        headers=bearer(token),
    )

    assert response.status_code == 200

    assert response.json() == {
        "authenticated": True,
    }

    assert response.headers["cache-control"] == "no-store"


def test_missing_session_token(environment):

    client, _, _ = environment

    assert client.get(SESSION).status_code == 401


def test_unknown_session(environment):

    client, _, _ = environment

    response = client.get(
        SESSION,
        headers=bearer("a" * 43),
    )

    assert response.status_code == 401


def test_session_requires_gateway(environment):

    client, _, _ = environment

    token = login(client).json()["session_token"]

    response = TestClient(app).get(
        SESSION,
        headers=bearer(token),
    )

    assert response.status_code == 403


def test_session_expiration(environment):

    client, _, now = environment

    token = login(client).json()["session_token"]

    now[0] += IDLE_TIMEOUT

    response = client.get(
        SESSION,
        headers=bearer(token),
    )

    assert response.status_code == 401


def test_logout_revokes_session(environment):

    client, _, _ = environment

    token = login(client).json()["session_token"]

    response = client.post(
        LOGOUT,
        headers=bearer(token),
    )

    assert response.status_code == 200

    assert response.json() == {
        "authenticated": False,
    }

    response = client.get(
        SESSION,
        headers=bearer(token),
    )

    assert response.status_code == 401


def test_logout_without_token(environment):

    client, _, _ = environment

    assert client.post(LOGOUT).status_code == 401


def test_logout_requires_gateway(environment):

    client, _, _ = environment

    token = login(client).json()["session_token"]

    response = TestClient(app).post(
        LOGOUT,
        headers=bearer(token),
    )

    assert response.status_code == 403


def test_login_rate_limit(environment):

    client, _, _ = environment

    for _ in range(5):

        response = client.post(
            LOGIN,
            json={
                "username": USERNAME,
                "password": "Incorrect password",
            },
        )

        assert response.status_code == 401

    response = login(client)

    assert response.status_code == 429
    assert "retry-after" in response.headers


def test_database_failure_blocks_login(environment):

    client, path, _ = environment

    path.chmod(0o644)

    response = login(client)

    assert response.status_code == 503

    assert response.json() == {
        "detail": "Authentication unavailable",
    }


def test_database_failure_blocks_session(environment):

    client, path, _ = environment

    token = login(client).json()["session_token"]

    path.chmod(0o644)

    response = client.get(
        SESSION,
        headers=bearer(token),
    )

    assert response.status_code == 503


def test_no_public_registration(environment):

    client, _, _ = environment

    response = client.post(
        "/api/v1/auth/register",
        json={},
    )

    assert response.status_code == 404


def test_no_remote_password_reset(environment):

    client, _, _ = environment

    response = client.post(
        "/api/v1/auth/reset-password",
        json={},
    )

    assert response.status_code == 404
