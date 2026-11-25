"""Regression coverage for the shared public runtime."""

import pytest

from fastapi.testclient import TestClient

from aegis.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")
    monkeypatch.setenv("AEGIS_AI_ENABLED", "0")
    monkeypatch.setenv("AEGIS_GATEWAY_TOKEN", "a" * 64)

    with TestClient(app) as test_client:
        yield test_client


GATEWAY = {"x-aegis-gateway-token": "a" * 64}


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == "public"


@pytest.mark.parametrize("query", [
    "",
    "?id=search",
    "?id=systems",
    "?id=project",
    "?id=invalid",
    "?id=search&id=project",
    "?id=search&message=synthetic",
])
def test_recorded_examples_unavailable(client, query):
    response = client.get(
        "/example" + query,
        headers=GATEWAY,
    )

    assert response.status_code in (401, 404)
    assert "recorded_demo" not in response.text
    assert "synthetic" not in response.text


@pytest.mark.parametrize("endpoint", [
    "chat",
    "conversation",
    "inference",
])
def test_public_ai_denied(client, endpoint):
    response = client.post(
        "/api/v1/" + endpoint,
        headers=GATEWAY,
        json={},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("endpoint", [
    "/api/v1/status",
    "/api/v1/auth/session",
    "/api/v1/settings",
    "/api/v1/workspaces/tasks",
])
def test_public_data_requires_session(client, endpoint):
    response = client.get(
        endpoint,
        headers=GATEWAY,
    )

    assert response.status_code == 401


def test_public_owner_login_denied(client):
    response = client.post(
        "/api/v1/auth/login",
        headers=GATEWAY,
        json={},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("endpoint", [
    "/docs",
    "/openapi.json",
    "/redoc",
])
def test_public_documentation_not_exposed(client, endpoint):
    response = client.get(endpoint, headers=GATEWAY)

    assert response.status_code in (401, 404)


def test_public_session_requires_gateway(client):
    response = client.post("/api/v1/auth/guest")

    assert response.status_code == 403
