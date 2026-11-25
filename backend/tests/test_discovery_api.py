import pytest

from fastapi.testclient import TestClient

from aegis.main import app

from aegis.schemas.discovery import JobListing
from aegis.services import job_refresh
from aegis.storage import discovery as storage
from aegis.storage.database import connect


PREFIX = "/api/v1/career"

SOURCE = {
    "provider": "lever",
    "board": "synthetic",
    "company": "Synthetic Company",
    "enabled": True,
}


def add_source(client):
    response = client.post(
        PREFIX + "/sources",
        json=SOURCE,
    )

    assert response.status_code == 200
    return response.json()


def add_listing(client, path):
    source = add_source(client)

    storage.cache_snapshot(
        1,
        source["id"],
        source["revision"],
        [JobListing(
            external_id="synthetic-id",
            title="Software Engineer",
            location="San Francisco",
            description="Python and SQL",
            posting_url=(
                "https://jobs.lever.co/"
                "synthetic/synthetic-id"
            ),
        )],
        path,
    )

    response = client.get(PREFIX + "/jobs")

    assert response.status_code == 200

    return source, response.json()["jobs"][0]


def test_source_api_lifecycle(
    authenticated_environment,
):
    client, _, _, _, _ = authenticated_environment

    source = add_source(client)

    assert len(client.get(
        PREFIX + "/sources",
    ).json()["sources"]) == 1

    response = client.post(
        PREFIX + "/sources",
        json=SOURCE,
    )

    assert response.status_code == 409

    response = client.post(
        PREFIX + "/source",
        json={
            "id": source["id"],
            "action": "update",
            "expected_revision": 1,
            "source": {
                **SOURCE,
                "enabled": False,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["enabled"] == 0
    assert response.json()["revision"] == 2

    response = client.post(
        PREFIX + "/source",
        json={
            "id": source["id"],
            "action": "delete",
            "expected_revision": 2,
        },
    )

    assert response.status_code == 200

    assert client.get(
        PREFIX + "/sources",
    ).json()["sources"] == []


def test_listing_search_and_detail(
    authenticated_environment,
):
    client, _, _, path, _ = authenticated_environment

    _, job = add_listing(client, path)

    response = client.get(
        PREFIX + "/jobs",
        params={
            "q": "Python",
            "provider": "lever",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["jobs"]) == 1

    response = client.get(
        PREFIX + "/job",
        params={"id": job["id"]},
    )

    assert response.status_code == 200
    assert response.json()["description"] == "Python and SQL"
    assert "no-store" in response.headers["cache-control"]


def test_save_job_is_idempotent(
    authenticated_environment,
):
    client, _, _, path, _ = authenticated_environment

    _, job = add_listing(client, path)

    first = client.post(
        PREFIX + "/job",
        json={"id": job["id"]},
    )

    second = client.post(
        PREFIX + "/job",
        json={"id": job["id"]},
    )

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json()["created"] is True
    assert second.json()["created"] is False

    assert (
        first.json()["application_id"]
        == second.json()["application_id"]
    )

    response = client.get(
        "/api/v1/workspaces/jobs",
    )

    records = response.json()["records"]

    assert len(records) == 1
    assert records[0]["status"] == "saved"
    assert records[0]["title"] == job["title"]

    with connect(path) as c:
        assert c.execute("""
            SELECT COUNT(*) FROM workspace_audit_events
            WHERE workspace = 'jobs'
                AND event_type = 'created'
        """).fetchone()[0] == 1


def test_existing_manual_application_preserved(
    authenticated_environment,
):
    client, _, _, path, _ = authenticated_environment

    _, job = add_listing(client, path)

    manual = client.post(
        "/api/v1/workspaces/jobs",
        json={
            "title": "Existing application",
            "detail": "Synthetic Company",
            "status": "interview",
            "reference": job["posting_url"],
        },
    ).json()

    result = client.post(
        PREFIX + "/job",
        json={"id": job["id"]},
    )

    assert result.status_code == 200
    assert result.json()["created"] is False
    assert result.json()["application_id"] == manual["id"]

    records = client.get(
        "/api/v1/workspaces/jobs",
    ).json()["records"]

    assert len(records) == 1
    assert records[0]["status"] == "interview"
    assert records[0]["title"] == "Existing application"


def test_save_survives_source_deletion(
    authenticated_environment,
):
    client, _, _, path, _ = authenticated_environment

    source, job = add_listing(client, path)

    assert client.post(
        PREFIX + "/job",
        json={"id": job["id"]},
    ).status_code == 200

    assert client.post(
        PREFIX + "/source",
        json={
            "id": source["id"],
            "action": "delete",
            "expected_revision": 1,
        },
    ).status_code == 200

    assert client.get(
        PREFIX + "/jobs",
    ).json()["jobs"] == []

    assert len(client.get(
        "/api/v1/workspaces/jobs",
    ).json()["records"]) == 1


def test_refresh_api(
    authenticated_environment,
    monkeypatch,
):
    client, _, _, _, _ = authenticated_environment

    source = add_source(client)

    monkeypatch.setattr(
        job_refresh,
        "fetch_jobs",
        lambda source: [],
    )

    response = client.post(
        PREFIX + "/source",
        json={
            "id": source["id"],
            "action": "refresh",
            "expected_revision": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["result"] == "success"


@pytest.mark.parametrize("method,endpoint", [
    ("GET", "/sources"),
    ("POST", "/sources"),
    ("POST", "/source"),
    ("GET", "/jobs"),
    ("GET", "/job"),
    ("POST", "/job"),
])
def test_unauthenticated_denied(method, endpoint):
    with TestClient(app) as client:
        response = client.request(
            method, PREFIX + endpoint,
        )

    assert response.status_code in {401, 403}


@pytest.mark.parametrize("method,endpoint", [
    ("GET", "/sources"),
    ("POST", "/sources"),
    ("POST", "/source"),
    ("GET", "/jobs"),
    ("GET", "/job"),
    ("POST", "/job"),
])
def test_public_discovery_requires_authentication(
    method, endpoint, monkeypatch,
):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")
    monkeypatch.setenv("AEGIS_GATEWAY_TOKEN", "a" * 64)

    with TestClient(app) as client:
        response = client.request(
            method,
            PREFIX + endpoint,
            headers={"x-aegis-gateway-token": "a" * 64},
        )

    assert response.status_code == 401


@pytest.mark.parametrize("endpoint", [
    "/sources",
    "/source",
    "/job",
])
def test_foreign_origin_denied(
    authenticated_environment,
    endpoint,
):
    client, _, _, _, _ = authenticated_environment

    response = client.post(
        PREFIX + endpoint,
        json={},
        headers={
            "Origin": "https://example.invalid",
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize("query", [
    "?q=a&q=b",
    "?unknown=1",
    "?limit=101",
    "?offset=-1",
    "?provider=unknown",
])
def test_invalid_queries(
    authenticated_environment,
    query,
):
    client, _, _, _, _ = authenticated_environment

    assert client.get(
        PREFIX + "/jobs" + query,
    ).status_code == 422


def test_invalid_source_identifier(
    authenticated_environment,
):
    client, _, _, _, _ = authenticated_environment

    response = client.post(
        PREFIX + "/sources",
        json={
            **SOURCE,
            "board": "https://example.invalid",
        },
    )

    assert response.status_code == 422


def test_duplicate_json_keys_rejected(
    authenticated_environment,
):
    client, _, _, _, _ = authenticated_environment

    response = client.post(
        PREFIX + "/sources",
        content=(
            '{"provider":"lever",'
            '"provider":"ashby",'
            '"board":"synthetic",'
            '"company":"Synthetic"}'
        ),
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422


def test_request_size_limit(
    authenticated_environment,
):
    client, _, _, _, _ = authenticated_environment

    response = client.post(
        PREFIX + "/sources",
        content="x" * 8193,
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 413


def test_invalid_action_payload(
    authenticated_environment,
):
    client, _, _, _, _ = authenticated_environment

    source = add_source(client)

    response = client.post(
        PREFIX + "/source",
        json={
            "id": source["id"],
            "action": "refresh",
            "expected_revision": 1,
            "source": SOURCE,
        },
    )

    assert response.status_code == 422


def test_discovery_api_filters(authenticated_environment):
    client, _, _, path, _ = authenticated_environment

    add_listing(client, path)

    response = client.get(
        PREFIX + "/jobs",
        params={
            "location": "San Francisco",
            "freshness": "fresh",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["jobs"]) == 1

    response = client.get(
        PREFIX + "/jobs",
        params={"location": "Seattle"},
    )

    assert response.status_code == 200
    assert response.json()["jobs"] == []


@pytest.mark.parametrize("query", [
    "?freshness=unknown",
    "?freshness=all&freshness=fresh",
    "?location=a&location=b",
    "?location=%00",
])
def test_invalid_discovery_filters(
    authenticated_environment, query,
):
    client, _, _, _, _ = authenticated_environment

    assert client.get(
        PREFIX + "/jobs" + query,
    ).status_code == 422


def test_emergency_stop_blocks_discovery_network(
    authenticated_environment,
    monkeypatch,
):
    from aegis.storage.settings import (
        load_settings,
        save_settings,
    )

    client, _, _, path, _ = authenticated_environment

    source, job = add_listing(client, path)

    current = load_settings(path)

    save_settings(
        current.settings.model_copy(
            update={"emergency_stop": True}
        ),
        current.revision,
        path,
    )

    def forbidden_fetch(*args):
        pytest.fail(
            "Emergency stop permitted outbound request"
        )

    monkeypatch.setattr(
        job_refresh,
        "fetch_jobs",
        forbidden_fetch,
    )

    # Remove cooldown only in the isolated test database.
    with connect(path) as c:
        c.execute("""
            UPDATE job_sources
            SET last_attempt_at = NULL
            WHERE id = ?
        """, (source["id"],))

    response = client.post(
        PREFIX + "/source",
        json={
            "id": source["id"],
            "action": "refresh",
            "expected_revision": source["revision"],
            "force": True,
        },
    )

    assert response.status_code == 403

    assert client.get(
        PREFIX + "/jobs",
    ).status_code == 200

    assert client.get(
        PREFIX + "/job",
        params={"id": job["id"]},
    ).status_code == 200

    assert len(client.get(
        PREFIX + "/jobs",
    ).json()["jobs"]) == 1

    assert not job_refresh.ACTIVE_REFRESHES
