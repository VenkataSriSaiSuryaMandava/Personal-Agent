import pytest

from fastapi import HTTPException
from fastapi.testclient import TestClient

from aegis.main import app
from aegis.security.runtime_policy import (
    ai_enabled,
    require_ai_enabled,
)


@pytest.fixture(autouse=True)
def clean_runtime(monkeypatch):
    for name in (
        "AEGIS_RUNTIME_MODE",
        "AEGIS_PUBLIC_DEMO",
        "AEGIS_AI_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_existing_private_default():
    assert ai_enabled()


def test_private_ai_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "private")
    monkeypatch.setenv("AEGIS_AI_ENABLED", "1")

    assert ai_enabled()


def test_private_ai_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AEGIS_AI_ENABLED", "0")

    assert not ai_enabled()


@pytest.mark.parametrize("flag", ["0", "1", "", "invalid"])
def test_public_mode_cannot_enable_ai(monkeypatch, flag):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")
    monkeypatch.setenv("AEGIS_AI_ENABLED", flag)

    assert not ai_enabled()

    with pytest.raises(HTTPException) as error:
        require_ai_enabled()

    assert error.value.status_code == 403


def test_legacy_public_mode_blocks_ai(monkeypatch):
    monkeypatch.setenv("AEGIS_PUBLIC_DEMO", "1")
    monkeypatch.setenv("AEGIS_AI_ENABLED", "1")

    assert not ai_enabled()


@pytest.mark.parametrize(
    "endpoint",
    ["chat", "inference", "conversation"],
)
def test_public_ai_routes_denied(monkeypatch, endpoint):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")
    monkeypatch.setenv("AEGIS_AI_ENABLED", "1")
    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/{endpoint}",
            json={},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "AI is disabled in this deployment"
    )


def test_invalid_ai_flag_fails_closed(monkeypatch):
    monkeypatch.setenv("AEGIS_AI_ENABLED", "invalid")

    assert not ai_enabled()
