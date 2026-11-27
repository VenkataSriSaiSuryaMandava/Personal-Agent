"""Authenticated workflow lifecycle and isolation tests."""

from uuid import uuid4

import pytest

from fastapi.testclient import TestClient

from aegis.main import app


BASE = "/api/v1/workflows"


def create_source(client, headers=None):
    result = client.post(
        "/api/v1/career/sources",
        headers=headers,
        json={
            "provider": "greenhouse",
            "board": "workflow-synthetic",
            "company": "Synthetic Workflow Company",
        },
    )

    assert result.status_code == 200
    return result.json()["id"]


def payload(source_id, key=None):
    return {
        "workflow_type": "company_summary",
        "target_id": source_id,
        "request_key": key or str(uuid4()),
    }


def create_run(client, headers=None):
    source_id = create_source(client, headers)

    result = client.post(
        BASE,
        headers=headers,
        json=payload(source_id),
    )

    assert result.status_code == 200
    return result.json()


@pytest.mark.parametrize("method,suffix", [
    ("GET", ""),
    ("POST", ""),
    ("GET", "/{id}"),
    ("GET", "/{id}/events"),
    ("POST", "/{id}/execute"),
    ("POST", "/{id}/cancel"),
])
def test_workflow_gateway_required(method, suffix):
    with TestClient(app) as client:
        response = client.request(
            method,
            BASE + suffix.format(id=str(uuid4())),
        )

    assert response.status_code == 403


@pytest.mark.parametrize("method,suffix", [
    ("GET", ""),
    ("POST", ""),
    ("GET", "/{id}"),
    ("GET", "/{id}/events"),
    ("POST", "/{id}/execute"),
    ("POST", "/{id}/cancel"),
])
def test_workflow_session_required(
    authenticated_environment,
    method,
    suffix,
):
    owner, _, _, _, _ = authenticated_environment

    with TestClient(app) as client:
        response = client.request(
            method,
            BASE + suffix.format(id=str(uuid4())),
            headers={
                "x-aegis-gateway-token":
                    owner.headers["x-aegis-gateway-token"],
            },
        )

    assert response.status_code == 401


def test_workflow_lifecycle(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    source_id = create_source(client)
    request = payload(source_id)

    created = client.post(BASE, json=request)

    assert created.status_code == 200
    assert created.headers["cache-control"] == "no-store"

    run = created.json()
    identifier = run["id"]
    url = BASE + "/" + identifier

    assert run["status"] == "queued"

    duplicate = client.post(BASE, json=request)

    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == identifier

    records = client.get(BASE).json()["records"]

    assert len(records) == 1

    execution = client.post(url + "/execute")

    assert execution.status_code == 200

    result = execution.json()

    assert result["status"] == "completed"
    assert result["steps"][0]["attempt_count"] == 1

    output = result["steps"][0]["output"]

    assert output["company"] == (
        "Synthetic Workflow Company"
    )

    assert output["identity_verified"] is False

    for step in result["steps"]:
        assert "lease_token" not in step
        assert "input_payload" not in step

    repeated = client.post(url + "/execute")

    assert repeated.status_code == 200
    assert repeated.json()["steps"][0]["attempt_count"] == 1

    events = client.get(url + "/events")

    assert events.status_code == 200

    assert [
        event["event_type"]
        for event in events.json()["events"]
    ] == [
        "workflow.created",
        "workflow.started",
        "workflow.completed",
    ]


def test_workflow_cancel(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    run = create_run(client)
    url = BASE + "/" + run["id"]

    cancelled = client.post(
        url + "/cancel",
        json={"expected_revision": run["revision"]},
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    executed = client.post(url + "/execute")

    assert executed.status_code == 200
    assert executed.json()["status"] == "cancelled"
    assert executed.json()["steps"][0]["attempt_count"] == 0


def test_workflow_unknown_target(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    response = client.post(
        BASE,
        json=payload(str(uuid4())),
    )

    assert response.status_code == 404


def test_workflow_foreign_origin(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    response = client.post(
        BASE,
        json=payload(str(uuid4())),
        headers={"Origin": "https://example.invalid"},
    )

    assert response.status_code == 403


def test_workflow_invalid_query(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    for query in (
        "?limit=101",
        "?limit=1&limit=2",
        "?offset=-1",
        "?user_id=2",
        "?path=private",
    ):
        assert client.get(
            BASE + query,
        ).status_code == 422


@pytest.mark.parametrize("extra", [
    {"user_id": 2},
    {"handler": "arbitrary"},
    {"scoped_grant": True},
    {"path": "/private"},
    {"destination": "https://example.invalid"},
])
def test_workflow_extra_fields_rejected(
    authenticated_environment,
    extra,
):
    client, _, _, _, _ = authenticated_environment

    response = client.post(
        BASE,
        json={
            **payload(str(uuid4())),
            **extra,
        },
    )

    assert response.status_code == 422


def test_execution_rejects_body(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    run = create_run(client)

    response = client.post(
        BASE + "/" + run["id"] + "/execute",
        json={"capability": "external.send"},
    )

    assert response.status_code == 422


def test_execution_emergency_stop(
    authenticated_environment,
    monkeypatch,
):
    client, _, _, _, _ = authenticated_environment

    run = create_run(client)
    url = BASE + "/" + run["id"]

    monkeypatch.setenv("AEGIS_EMERGENCY_STOP", "1")

    response = client.post(url + "/execute")

    assert response.status_code == 403

    detail = client.get(url).json()

    assert detail["status"] == "queued"
    assert detail["steps"][0]["attempt_count"] == 0


def test_expired_workflow_session(
    authenticated_environment,
):
    client, _, _, _, now = authenticated_environment

    run = create_run(client)

    now[0] += 86400

    response = client.post(
        BASE + "/" + run["id"] + "/execute",
    )

    assert response.status_code == 401


def test_persisted_emergency_stop_blocks_workflows(
    authenticated_environment,
    monkeypatch,
):
    from aegis.api import settings as settings_api
    from aegis.services.settings import SettingsService
    from aegis.storage.settings import load_settings

    client, _, _, path, _ = authenticated_environment

    monkeypatch.setattr(
        settings_api,
        "service",
        SettingsService(path),
    )

    monkeypatch.setenv("AEGIS_EMERGENCY_STOP", "0")

    run = create_run(client)
    url = BASE + "/" + run["id"]

    snapshot = load_settings(path)

    stopped = client.patch(
        "/api/v1/settings",
        json={
            "expected_revision": snapshot.revision,
            "changes": {"emergency_stop": True},
        },
    )

    assert stopped.status_code == 200
    assert load_settings(path).settings.emergency_stop is True

    blocked = client.post(url + "/execute")

    assert blocked.status_code == 403

    blocked_create = client.post(
        BASE,
        json=payload(run["target_id"]),
    )

    assert blocked_create.status_code == 403

    detail = client.get(url).json()

    assert detail["status"] == "queued"
    assert detail["steps"][0]["attempt_count"] == 0

    cancelled = client.post(
        url + "/cancel",
        json={
            "expected_revision": detail["revision"],
        },
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
