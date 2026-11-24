import pytest

from fastapi.testclient import TestClient

from aegis.api import settings as settings_api
from aegis.main import app

from aegis.services.settings import SettingsService

from aegis.storage.database import connect
from aegis.storage.settings import (
    ApplicationSettings,
    load_settings,
    save_settings,
)


BASE = "/api/v1/settings"


@pytest.fixture
def settings_client(
    authenticated_environment,
    monkeypatch,
):

    client, auth, token, path, now = (
        authenticated_environment
    )

    monkeypatch.setattr(
        settings_api,
        "service",
        SettingsService(path),
    )

    return client, path


def patch(client, changes, revision=1):

    return client.patch(
        BASE,
        json={
            "expected_revision": revision,
            "changes": changes,
        },
    )


@pytest.mark.parametrize("method,suffix", [
    ("GET", ""),
    ("PATCH", ""),
    ("POST", "/reset"),
    ("GET", "/providers"),
    ("GET", "/audit"),
    ("GET", "/storage"),
])
def test_gateway_required(
    settings_client,
    method,
    suffix,
):

    with TestClient(app) as anonymous:

        response = anonymous.request(
            method,
            BASE + suffix,
        )

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_owner_session_required(settings_client):

    client, _ = settings_client

    with TestClient(
        app,
        headers={
            "x-aegis-gateway-token": (
                client.headers["x-aegis-gateway-token"]
            )
        },
    ) as anonymous:

        response = anonymous.get(BASE)

    assert response.status_code == 401


def test_foreign_origin_rejected(settings_client):

    client, _ = settings_client

    response = client.get(
        BASE,
        headers={"origin": "https://example.invalid"},
    )

    assert response.status_code == 403


def test_duplicate_auth_headers_rejected(settings_client):

    client, _ = settings_client

    response = client.get(
        BASE,
        headers=[
            ("authorization", client.headers["authorization"]),
            ("authorization", client.headers["authorization"]),
        ],
    )

    assert response.status_code == 400


def test_get_settings(settings_client):

    client, _ = settings_client

    response = client.get(BASE)

    assert response.status_code == 200

    data = response.json()

    assert data["revision"] == 1
    assert data["settings"]["theme"] == "dark"

    assert set(data["editable_fields"]) == {
        "theme",
        "startup_workspace",
        "response_style",
        "cloud_enabled",
        "emergency_stop",
        "retain_conversations",
    }

    assert data["security_enforcement_active"] is True


def test_response_security_headers(settings_client):

    client, _ = settings_client

    response = client.get(BASE)

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_patch_persists(settings_client):

    client, path = settings_client

    response = patch(
        client,
        {"theme": "light"},
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 2

    assert load_settings(path).settings.theme == "light"


def test_multiple_preferences(settings_client):

    client, path = settings_client

    response = patch(client, {
        "startup_workspace": "chat",
        "response_style": "detailed",
        "theme": "system",
    })

    assert response.status_code == 200

    saved = load_settings(path).settings

    assert saved.theme == "system"
    assert saved.startup_workspace == "chat"
    assert saved.response_style == "detailed"


def test_stale_revision(settings_client):

    client, path = settings_client

    assert patch(
        client,
        {"theme": "light"},
    ).status_code == 200

    response = patch(
        client,
        {"theme": "system"},
    )

    assert response.status_code == 409
    assert load_settings(path).settings.theme == "light"


def test_no_op_update(settings_client):

    client, _ = settings_client

    response = patch(
        client,
        {"theme": "dark"},
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 1


@pytest.mark.parametrize("changes", [
    {"theme": "unknown"},
    {"theme": None},
    {"theme": True},
    {"response_style": "unknown"},
    {"startup_workspace": "unknown"},
    {"unknown": True},
    {"primary_provider": "groq"},
    {"fallback_provider": "gemini"},
    {"fallback_enabled": True},
    {"retain_conversations": "true"},
    {},
])
def test_invalid_or_unimplemented_changes(
    settings_client,
    changes,
):

    client, path = settings_client

    response = patch(client, changes)

    assert response.status_code == 422
    assert load_settings(path).revision == 1


@pytest.mark.parametrize("revision", [
    0,
    -1,
    True,
    "1",
    9223372036854775808,
])
def test_invalid_revision(settings_client, revision):

    client, _ = settings_client

    response = patch(
        client,
        {"theme": "light"},
        revision,
    )

    assert response.status_code == 422


def test_reject_unknown_request_fields(settings_client):

    client, _ = settings_client

    response = client.patch(BASE, json={
        "expected_revision": 1,
        "changes": {"theme": "light"},
        "extra": True,
    })

    assert response.status_code == 422


def test_wrong_content_type(settings_client):

    client, _ = settings_client

    response = client.patch(
        BASE,
        content="test",
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 415


def test_oversized_body(settings_client):

    client, _ = settings_client

    response = client.patch(
        BASE,
        content=b"x" * 4097,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413


@pytest.mark.parametrize("payload", [
    b"{invalid-json",
    b"\xff",
    b'{"expected_revision":1,"expected_revision":2,"changes":{"theme":"light"}}',
    b'{"expected_revision":1,"changes":{"theme":"dark","theme":"light"}}',
    b'{"expected_revision":1,"changes":{"theme":NaN}}',
])
def test_invalid_json(settings_client, payload):

    client, _ = settings_client

    response = client.patch(
        BASE,
        content=payload,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422


def test_reset_general_preferences(settings_client):

    client, path = settings_client

    assert patch(
        client,
        {"theme": "light"},
    ).status_code == 200

    response = client.post(
        BASE + "/reset",
        json={"expected_revision": 2},
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 3

    assert load_settings(path).settings.theme == "dark"


def test_reset_preserves_security_preferences(
    settings_client,
):

    client, path = settings_client

    save_settings(
        ApplicationSettings(
            theme="light",
            emergency_stop=True,
            cloud_enabled=True,
        ),
        1,
        path,
    )

    response = client.post(
        BASE + "/reset",
        json={"expected_revision": 2},
    )

    assert response.status_code == 200

    saved = load_settings(path).settings

    assert saved.theme == "dark"
    assert saved.emergency_stop is True
    assert saved.cloud_enabled is True


def test_reset_stale_revision(settings_client):

    client, _ = settings_client

    response = client.post(
        BASE + "/reset",
        json={"expected_revision": 99},
    )

    assert response.status_code == 409


def test_providers_not_configured(
    settings_client,
    monkeypatch,
):

    client, _ = settings_client

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    response = client.get(BASE + "/providers")

    assert response.status_code == 200

    data = response.json()

    assert data["providers"][0]["configured"] is False
    assert data["providers"][1]["implemented"] is False
    assert data["fallback_implemented"] is False


def test_provider_credentials_never_exposed(
    settings_client,
    monkeypatch,
):

    client, _ = settings_client

    synthetic = "synthetic-value-for-masking-test"

    monkeypatch.setenv("GEMINI_API_KEY", synthetic)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    response = client.get(BASE + "/providers")

    assert response.status_code == 200
    assert synthetic not in response.text

    gemini = response.json()["providers"][0]

    assert gemini["configured"] is True
    assert gemini["live_verified"] is False


def test_invalid_model_configuration(
    settings_client,
    monkeypatch,
):

    client, _ = settings_client

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic")
    monkeypatch.setenv("GEMINI_MODEL", "invalid-model")

    response = client.get(BASE + "/providers")

    assert response.json()["providers"][0]["status"] == (
        "invalid_configuration"
    )


def test_empty_audit(settings_client):

    client, _ = settings_client

    response = client.get(BASE + "/audit")

    assert response.status_code == 200

    assert response.json() == {
        "events": [],
        "next_before_id": None,
    }


def test_audit_pagination(settings_client):

    client, _ = settings_client

    assert patch(
        client,
        {"theme": "light"},
    ).status_code == 200

    assert patch(
        client,
        {"theme": "system"},
        2,
    ).status_code == 200

    first = client.get(
        BASE + "/audit?limit=1"
    ).json()

    assert len(first["events"]) == 1

    event = first["events"][0]

    assert event["event_type"] == "settings.updated"
    assert event["settings_revision"] == 3

    assert set(event) == {
        "id",
        "event_type",
        "settings_revision",
        "created_at",
    }

    cursor = first["next_before_id"]

    second = client.get(
        BASE + f"/audit?limit=1&before_id={cursor}"
    ).json()

    assert len(second["events"]) == 1

    assert second["events"][0]["settings_revision"] == 2
    assert second["next_before_id"] is None


@pytest.mark.parametrize("query", [
    "limit=0",
    "limit=101",
    "limit=abc",
    "limit=-1",
    "limit=1&limit=2",
    "before_id=0",
    "before_id=-1",
    "before_id=9223372036854775808",
    "unknown=1",
])
def test_invalid_audit_queries(settings_client, query):

    client, _ = settings_client

    response = client.get(BASE + "/audit?" + query)

    assert response.status_code == 422


def test_storage_status(settings_client):

    client, path = settings_client

    response = client.get(BASE + "/storage")

    assert response.status_code == 200

    data = response.json()

    assert data["schema_version"] == 6
    assert data["integrity"] == "ok"
    assert data["local_only"] is True
    assert data["encrypted_by_application"] is False

    assert str(path) not in response.text


def test_missing_settings_returns_503(settings_client):

    client, path = settings_client

    with connect(path) as connection:
        connection.execute(
            "DELETE FROM application_settings"
        )

    response = client.get(BASE)

    assert response.status_code == 503
    assert response.json()["detail"] == "Settings unavailable"


def test_revoked_session_rejected(settings_client):

    client, _ = settings_client

    result = client.post("/api/v1/auth/logout")

    assert result.status_code == 200

    assert client.get(BASE).status_code == 401


def test_no_private_database_changes_during_tests(
    settings_client,
):

    client, path = settings_client

    assert settings_api.service.path == path

    assert client.get(BASE).status_code == 200


def test_retention_preference(settings_client):
    client, path = settings_client

    assert load_settings(path).settings.retain_conversations is False

    response = patch(
        client,
        {"retain_conversations": True},
    )

    assert response.status_code == 200
    assert load_settings(path).settings.retain_conversations is True

    response = patch(
        client,
        {"retain_conversations": False},
        2,
    )

    assert response.status_code == 200
    assert load_settings(path).settings.retain_conversations is False
