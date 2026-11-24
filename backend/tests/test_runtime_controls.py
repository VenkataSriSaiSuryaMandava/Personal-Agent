import os

from unittest.mock import Mock

import pytest

from aegis.api import settings as settings_api
from aegis.security.gateway import GatewayDenied
from aegis.security.runtime_controls import runtime_controls
from aegis.services import conversation, inference
from aegis.services.settings import SettingsService
from aegis.storage.database import connect
from aegis.storage.settings import (
    ApplicationSettings,
    load_settings,
    save_settings,
)


@pytest.fixture
def secure_runtime(authenticated_environment, monkeypatch):
    client, _, _, path, _ = authenticated_environment

    monkeypatch.setattr(runtime_controls, "path", path)
    monkeypatch.setattr(
        settings_api,
        "service",
        SettingsService(path),
    )

    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")
    monkeypatch.setenv("AEGIS_CUSTOM_CLOUD_ENABLED", "1")
    monkeypatch.setenv("AEGIS_EMERGENCY_STOP", "0")
    monkeypatch.setenv("AEGIS_DEMO_MODE", "0")
    monkeypatch.setenv("GEMINI_MODEL", inference.ALLOWED_MODEL)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-fixture")
    monkeypatch.setenv("AEGIS_UNLIMITED_AI", "1")

    return client, path


def update(client, changes, revision):
    return client.patch(
        "/api/v1/settings",
        json={
            "changes": changes,
            "expected_revision": revision,
        },
    )


def inference_payload():
    return {
        "prompt_id": "general_knowledge",
        "approved": True,
    }


def conversation_payload():
    return {
        "message": "Explain binary search",
        "history": [],
        "classification": "public",
        "approved": True,
    }


def test_default_deny(secure_runtime):
    client, _ = secure_runtime

    provider = Mock()
    original = inference.GeminiProvider

    inference.GeminiProvider = provider

    try:
        response = client.post(
            "/api/v1/inference",
            json=inference_payload(),
        )
        assert response.status_code == 403
        provider.assert_not_called()
    finally:
        inference.GeminiProvider = original


def test_owner_can_enable_cloud(secure_runtime):
    client, path = secure_runtime

    result = update(
        client,
        {"cloud_enabled": True},
        1,
    )

    assert result.status_code == 200
    assert result.json()["revision"] == 2
    assert load_settings(path).settings.cloud_enabled is True

    runtime_controls.require_cloud()


def test_owner_can_disable_cloud(secure_runtime):
    client, path = secure_runtime

    assert update(
        client, {"cloud_enabled": True}, 1
    ).status_code == 200

    assert update(
        client, {"cloud_enabled": False}, 2
    ).status_code == 200

    assert load_settings(path).settings.cloud_enabled is False

    with pytest.raises(GatewayDenied):
        runtime_controls.require_cloud()


def test_emergency_stop_immediately_denies(secure_runtime):
    client, path = secure_runtime

    assert update(
        client, {"cloud_enabled": True}, 1
    ).status_code == 200

    runtime_controls.require_cloud()

    response = update(
        client, {"emergency_stop": True}, 2
    )

    assert response.status_code == 200
    assert load_settings(path).settings.emergency_stop is True

    with pytest.raises(GatewayDenied):
        runtime_controls.require_cloud()


def test_emergency_stop_can_be_disabled(secure_runtime):
    client, path = secure_runtime

    assert update(
        client,
        {
            "cloud_enabled": True,
            "emergency_stop": True,
        },
        1,
    ).status_code == 200

    with pytest.raises(GatewayDenied):
        runtime_controls.require_cloud()

    assert update(
        client, {"emergency_stop": False}, 2
    ).status_code == 200

    runtime_controls.require_cloud()

    assert load_settings(path).settings.emergency_stop is False


@pytest.mark.parametrize("variable,value", [
    ("AEGIS_CLOUD_ENABLED", "0"),
    ("AEGIS_EMERGENCY_STOP", "1"),
    ("AEGIS_DEMO_MODE", "1"),
])
def test_environment_restriction_wins(
    secure_runtime,
    monkeypatch,
    variable,
    value,
):
    client, _ = secure_runtime

    assert update(
        client, {"cloud_enabled": True}, 1
    ).status_code == 200

    monkeypatch.setenv(variable, value)

    with pytest.raises(GatewayDenied):
        runtime_controls.require_cloud()


@pytest.mark.parametrize("changes", [
    {"cloud_enabled": "true"},
    {"cloud_enabled": 1},
    {"cloud_enabled": None},
    {"emergency_stop": "false"},
    {"emergency_stop": 0},
    {"emergency_stop": None},
    {"primary_provider": "groq"},
    {"fallback_enabled": True},
    {"retain_conversations": "true"},
])
def test_invalid_security_changes(secure_runtime, changes):
    client, path = secure_runtime

    response = update(client, changes, 1)

    assert response.status_code == 422
    assert load_settings(path).revision == 1


def test_stale_security_revision(secure_runtime):
    client, path = secure_runtime

    assert update(
        client, {"cloud_enabled": True}, 1
    ).status_code == 200

    response = update(
        client, {"emergency_stop": True}, 1
    )

    assert response.status_code == 409
    assert load_settings(path).settings.emergency_stop is False


def test_general_reset_preserves_security(secure_runtime):
    client, path = secure_runtime

    assert update(
        client,
        {
            "cloud_enabled": True,
            "emergency_stop": True,
            "theme": "light",
        },
        1,
    ).status_code == 200

    response = client.post(
        "/api/v1/settings/reset",
        json={"expected_revision": 2},
    )

    assert response.status_code == 200

    saved = load_settings(path).settings

    assert saved.theme == "dark"
    assert saved.cloud_enabled is True
    assert saved.emergency_stop is True


def test_settings_absent_fails_closed(secure_runtime):
    _, path = secure_runtime

    with connect(path) as connection:
        connection.execute(
            "DELETE FROM application_settings"
        )

    with pytest.raises(GatewayDenied):
        runtime_controls.require_cloud()


def test_settings_corruption_fails_closed(secure_runtime):
    _, path = secure_runtime

    with connect(path) as connection:
        connection.execute(
            "UPDATE application_settings SET payload = ? WHERE id = 1",
            ("invalid-json",),
        )

    with pytest.raises(GatewayDenied):
        runtime_controls.require_cloud()


def test_inference_denied_without_provider(
    secure_runtime,
    monkeypatch,
):
    client, _ = secure_runtime

    provider = Mock()
    monkeypatch.setattr(
        inference,
        "GeminiProvider",
        provider,
    )

    result = client.post(
        "/api/v1/inference",
        json=inference_payload(),
    )

    assert result.status_code == 403
    provider.assert_not_called()


def test_inference_allowed_after_enable(
    secure_runtime,
    monkeypatch,
):
    client, _ = secure_runtime

    assert update(
        client, {"cloud_enabled": True}, 1
    ).status_code == 200

    provider = Mock()
    provider.return_value.complete.return_value = (
        "Synthetic response"
    )

    monkeypatch.setattr(
        inference,
        "GeminiProvider",
        provider,
    )

    result = client.post(
        "/api/v1/inference",
        json=inference_payload(),
    )

    assert result.status_code == 200
    assert result.json()["message"] == "Synthetic response"

    provider.return_value.complete.assert_called_once()


def test_conversation_blocked_after_stop(
    secure_runtime,
    monkeypatch,
):
    client, _ = secure_runtime

    assert update(
        client, {"cloud_enabled": True}, 1
    ).status_code == 200

    assert update(
        client, {"emergency_stop": True}, 2
    ).status_code == 200

    provider = Mock()
    monkeypatch.setattr(
        conversation,
        "GeminiProvider",
        provider,
    )

    result = client.post(
        "/api/v1/conversation",
        json=conversation_payload(),
    )

    assert result.status_code == 403
    provider.assert_not_called()


def test_conversation_allowed_after_enable(
    secure_runtime,
    monkeypatch,
):
    client, _ = secure_runtime

    assert update(
        client, {"cloud_enabled": True}, 1
    ).status_code == 200

    provider = Mock()
    provider.return_value.complete.return_value = (
        "Synthetic conversation answer"
    )

    monkeypatch.setattr(
        conversation,
        "GeminiProvider",
        provider,
    )

    result = client.post(
        "/api/v1/conversation",
        json=conversation_payload(),
    )

    assert result.status_code == 200
    assert result.json()["message"] == (
        "Synthetic conversation answer"
    )

    provider.return_value.complete.assert_called_once()


def test_audit_records_emergency_stop(secure_runtime):
    client, path = secure_runtime

    assert update(
        client, {"emergency_stop": True}, 1
    ).status_code == 200

    events = client.get("/api/v1/settings/audit").json()["events"]

    names = [item["event_type"] for item in events]

    assert "emergency_stop.enabled" in names
    assert "settings.updated" in names


def test_security_values_are_not_logged(secure_runtime):
    client, _ = secure_runtime

    assert update(
        client, {"cloud_enabled": True}, 1
    ).status_code == 200

    response = client.get("/api/v1/settings/audit")

    assert response.status_code == 200

    for event in response.json()["events"]:
        assert set(event) == {
            "id",
            "event_type",
            "settings_revision",
            "created_at",
        }


def test_unauthenticated_security_update_rejected(
    secure_runtime,
):
    client, _ = secure_runtime

    response = client.patch(
        "/api/v1/settings",
        json={
            "changes": {"emergency_stop": True},
            "expected_revision": 1,
        },
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401


def test_emergency_stop_denies_during_request(
    secure_runtime,
    monkeypatch,
):
    client, path = secure_runtime

    assert update(
        client, {"cloud_enabled": True}, 1
    ).status_code == 200

    provider = Mock()

    def complete(_prompt):
        current = load_settings(path)

        save_settings(
            current.settings.model_copy(
                update={"emergency_stop": True}
            ),
            current.revision,
            path,
        )
        return "Response generated before stop"

    provider.return_value.complete.side_effect = complete

    monkeypatch.setattr(
        inference,
        "GeminiProvider",
        provider,
    )

    result = client.post(
        "/api/v1/inference",
        json=inference_payload(),
    )

    # The request was already sent. The final response
    # is denied after detecting the updated stop state.
    assert result.status_code == 403

    assert load_settings(path).settings.emergency_stop is True
