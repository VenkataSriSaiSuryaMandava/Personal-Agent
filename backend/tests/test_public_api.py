import secrets

import pytest

from fastapi.testclient import TestClient

from aegis.main import app
from aegis.security.public_sessions import public_sessions


@pytest.fixture
def environment(monkeypatch):
    from aegis.api import auth
    from aegis.security import public_middleware
    from aegis.security.public_limits import PublicRequestLimits

    limits = PublicRequestLimits()

    monkeypatch.setattr(auth, "public_limits", limits)
    monkeypatch.setattr(
        public_middleware, "public_limits", limits,
    )

    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")
    monkeypatch.setenv("AEGIS_AI_ENABLED", "0")

    gateway = secrets.token_hex(32)
    monkeypatch.setenv("AEGIS_GATEWAY_TOKEN", gateway)

    public_sessions.close()

    try:
        with TestClient(app) as client:
            yield client, {
                "x-aegis-gateway-token": gateway,
            }
    finally:
        public_sessions.close()


def visitor(client, gateway):
    response = client.post(
        "/api/v1/auth/guest",
        headers=gateway,
    )

    assert response.status_code == 200

    return {
        **gateway,
        "Authorization": (
            "Bearer " + response.json()["session_token"]
        ),
    }


def test_public_requires_gateway(environment):
    client, _ = environment

    assert client.post(
        "/api/v1/auth/guest",
    ).status_code == 403


def test_public_requires_session(environment):
    client, gateway = environment

    for path in (
        "career/profile",
        "career/resumes",
        "career/jobs",
        "career/sources",
        "settings",
        "workspaces/tasks",
        "conversations",
    ):
        assert client.get(
            "/api/v1/" + path,
            headers=gateway,
        ).status_code == 401


def test_owner_login_denied(environment):
    client, gateway = environment

    assert client.post(
        "/api/v1/auth/login",
        headers=gateway,
        json={},
    ).status_code == 403


def test_private_mode_rejects_guest(environment, monkeypatch):
    client, gateway = environment

    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "private")

    assert client.post(
        "/api/v1/auth/guest",
        headers=gateway,
    ).status_code == 403


def test_guest_request_body_denied(environment):
    client, gateway = environment

    assert client.post(
        "/api/v1/auth/guest",
        headers=gateway,
        json={"user_id": 1},
    ).status_code == 422


def test_guest_origin_denied(environment):
    client, gateway = environment

    assert client.post(
        "/api/v1/auth/guest",
        headers={
            **gateway,
            "Origin": "https://example.invalid",
        },
    ).status_code == 403


def test_real_public_endpoints(environment):
    client, gateway = environment
    headers = visitor(client, gateway)

    for path in (
        "auth/session",
        "career/profile",
        "career/resumes",
        "career/jobs",
        "career/sources",
        "settings",
        "settings/storage",
        "settings/providers",
        "settings/audit",
        "workspaces/summary",
        "workspaces/tasks",
        "conversations",
    ):
        response = client.get(
            "/api/v1/" + path,
            headers=headers,
        )

        assert response.status_code == 200, path


def test_visitor_workspace_isolation(environment):
    client, gateway = environment

    first = visitor(client, gateway)
    second = visitor(client, gateway)

    url = "/api/v1/workspaces/tasks"

    response = client.post(
        url,
        headers=first,
        json={
            "title": "Synthetic visitor task",
            "status": "todo",
        },
    )

    assert response.status_code == 200

    a = client.get(url, headers=first).json()
    b = client.get(url, headers=second).json()

    assert "Synthetic visitor task" in str(a)
    assert "Synthetic visitor task" not in str(b)


def test_public_settings_isolation(environment):
    client, gateway = environment

    first = visitor(client, gateway)
    second = visitor(client, gateway)

    url = "/api/v1/settings"

    a = client.get(url, headers=first).json()
    b = client.get(url, headers=second).json()

    theme = (
        "light"
        if a["settings"]["theme"] == "dark"
        else "dark"
    )

    response = client.patch(
        url,
        headers=first,
        json={
            "changes": {"theme": theme},
            "expected_revision": a["revision"],
        },
    )

    assert response.status_code == 200
    assert response.json()["settings"]["theme"] == theme
    assert client.get(url, headers=second).json() == b


def test_public_logout_revokes_access(environment):
    client, gateway = environment
    headers = visitor(client, gateway)

    assert client.post(
        "/api/v1/auth/logout",
        headers=headers,
    ).status_code == 200

    assert client.get(
        "/api/v1/career/profile",
        headers=headers,
    ).status_code == 401


def test_authenticated_public_ai_denied(environment):
    client, gateway = environment
    headers = visitor(client, gateway)

    for path in ("chat", "inference", "conversation"):
        assert client.post(
            "/api/v1/" + path,
            headers=headers,
            json={},
        ).status_code == 403


def test_public_creation_rate_limit(environment):
    client, gateway = environment

    for _ in range(4):
        visitor(client, gateway)

    response = client.post(
        "/api/v1/auth/guest",
        headers=gateway,
    )

    assert response.status_code == 429


def test_public_concurrency_limit(environment):
    from aegis.security import public_middleware

    client, gateway = environment

    slots = public_middleware.public_limits.slots

    for _ in range(4):
        assert slots.acquire(blocking=False)

    try:
        assert client.get(
            "/api/v1/career/profile",
            headers=gateway,
        ).status_code == 429

        assert client.get(
            "/health"
        ).status_code == 200

    finally:
        for _ in range(4):
            slots.release()


def test_public_request_limit(environment):
    from aegis.security import public_middleware

    client, gateway = environment
    headers = visitor(client, gateway)

    token = headers["Authorization"].split(" ", 1)[1]

    for _ in range(120):
        assert public_middleware.public_limits.allow_request(
            token
        )

    assert client.get(
        "/api/v1/career/profile",
        headers=headers,
    ).status_code == 429


def test_shared_backend_public_health(environment):
    client, _ = environment

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == "public"


def test_public_status_cannot_enable_cloud(
    environment, monkeypatch,
):
    client, gateway = environment
    headers = visitor(client, gateway)

    monkeypatch.setenv("AEGIS_AI_ENABLED", "1")
    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")
    monkeypatch.setenv("AEGIS_DEMO_MODE", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    response = client.get(
        "/api/v1/status",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["cloud_requests_enabled"] is False


def test_public_ai_preferences_locked(environment):
    client, gateway = environment
    headers = visitor(client, gateway)
    url = "/api/v1/settings"

    response = client.get(url, headers=headers)
    assert response.status_code == 200

    snapshot = response.json()

    for field in (
        "cloud_enabled",
        "retain_conversations",
    ):
        assert field not in snapshot["editable_fields"]
        assert snapshot["settings"][field] is False

        for enabled in (True, False):
            denied = client.patch(
                url,
                headers=headers,
                json={
                    "changes": {field: enabled},
                    "expected_revision": snapshot["revision"],
                },
            )

            assert denied.status_code == 422

    assert client.get(
        url, headers=headers,
    ).json() == snapshot


def test_public_provider_metadata_disabled(
    environment, monkeypatch,
):
    client, gateway = environment
    headers = visitor(client, gateway)

    monkeypatch.setenv(
        "GEMINI_API_KEY", "synthetic-test-value",
    )
    monkeypatch.setenv("AEGIS_AI_ENABLED", "1")
    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")

    response = client.get(
        "/api/v1/settings/providers",
        headers=headers,
    )

    assert response.status_code == 200

    result = response.json()

    assert result["fallback_enabled"] is False

    for provider in result["providers"]:
        assert provider["configured"] is False
        assert provider["live_verified"] is False
        assert provider["model"] is None

    assert "synthetic-test-value" not in response.text


def test_public_storage_metadata(environment):
    client, gateway = environment
    headers = visitor(client, gateway)

    response = client.get(
        "/api/v1/settings/storage",
        headers=headers,
    )

    assert response.status_code == 200

    result = response.json()

    assert result["database"] == "sqlite"
    assert result["schema_version"] == 8
    assert result["integrity"] == "ok"
    assert result["local_only"] is False
    assert result["encrypted_by_application"] is False
