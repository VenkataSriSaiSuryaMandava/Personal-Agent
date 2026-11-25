from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aegis.main import app
from aegis.api import discovery as api
from aegis.schemas.career import (
    CareerProfile,
    ResumeMetadata,
)
from aegis.schemas.discovery import (
    JobListing,
    JobSourceInput,
)
from aegis.services.career_intelligence import analyze_job
from aegis.storage import career, discovery
from aegis.storage.database import connect


ENDPOINT = "/api/v1/career/match"


@pytest.fixture
def intelligence(authenticated_environment):
    client, _, _, path, _ = authenticated_environment

    source = discovery.create_source(
        1,
        JobSourceInput(
            provider="lever",
            board="synthetic",
            company="Synthetic Company",
        ),
        path,
    )

    discovery.cache_snapshot(
        1,
        source["id"],
        source["revision"],
        [JobListing(
            external_id="synthetic-job",
            title="Software Engineer",
            description=(
                "Required qualifications\n"
                "Python\nSQL\n"
                "Preferred qualifications\nDocker"
            ),
            location="San Francisco",
            department="Engineering",
            work_mode="remote",
            employment_type="Full-time",
            posting_url=(
                "https://jobs.lever.co/"
                "synthetic/synthetic-job"
            ),
        )],
        path,
    )

    job = discovery.list_jobs(
        1, path,
    )["jobs"][0]

    return client, path, source, job


def test_match_without_profile(intelligence):
    client, _, _, job = intelligence

    response = client.get(
        ENDPOINT, params={"id": job["id"]},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["matching"]["score"] is None
    assert data["profile_revision"] == 0
    assert data["resume"] is None

    assert data["company"]["open_listings"] == 1
    assert data["company"]["identity_verified"] is False

    assert "no-store" in response.headers["cache-control"]


def test_saved_profile_and_active_resume(intelligence):
    client, path, _, job = intelligence

    career.save_profile(
        1,
        CareerProfile(
            skills=["Python"],
            target_roles=["Software Engineer"],
            work_mode="remote",
            email="private@example.invalid",
        ),
        0,
        path,
    )

    metadata = ResumeMetadata(
        title="Synthetic active resume",
        media_type="text/plain",
    )

    active = career.create_resume(
        1,
        metadata,
        b"SQL experience\nPrivate synthetic resume text",
        path,
    )

    career.create_resume(
        1,
        metadata.model_copy(update={
            "title": "Inactive resume",
        }),
        b"Docker experience",
        path,
    )

    response = client.get(
        ENDPOINT, params={"id": job["id"]},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["profile_revision"] == 1
    assert data["resume"]["id"] == active["id"]
    assert data["resume"]["has_text"] is True

    qualifications = {
        item["skill"]: item
        for item in data["matching"]["qualifications"]
    }

    assert qualifications["Python"]["status"] == "profile_match"
    assert qualifications["SQL"]["status"] == "resume_mention"
    assert qualifications["Docker"]["status"] == "not_evidenced"

    assert "Private synthetic resume text" not in response.text
    assert "private@example.invalid" not in response.text
    assert "extracted_text" not in data["resume"]
    assert "document" not in data["resume"]


def test_profile_changes_recomputed(intelligence):
    client, path, _, job = intelligence

    first = client.get(
        ENDPOINT, params={"id": job["id"]},
    ).json()

    assert first["matching"]["score"] is None

    career.save_profile(
        1,
        CareerProfile(
            skills=["Python", "SQL"],
            target_roles=["Software Engineer"],
        ),
        0,
        path,
    )

    second = client.get(
        ENDPOINT, params={"id": job["id"]},
    ).json()

    assert second["profile_revision"] == 1
    assert second["matching"]["score"] == 100


def test_read_only_analysis(intelligence):
    _, path, _, job = intelligence

    with connect(path) as c:
        before = list(c.iterdump())

    analyze_job(1, job["id"], path)

    with connect(path) as c:
        after = list(c.iterdump())

    assert before == after


def test_owner_isolation(intelligence):
    _, path, _, job = intelligence

    with pytest.raises(discovery.SourceNotFound):
        analyze_job(2, job["id"], path)


def test_unknown_job(intelligence):
    client, _, _, _ = intelligence

    response = client.get(
        ENDPOINT, params={"id": str(uuid4())},
    )

    assert response.status_code == 404


def test_disabled_source(intelligence):
    client, path, source, job = intelligence

    discovery.update_source(
        1,
        source["id"],
        JobSourceInput(
            provider="lever",
            board="synthetic",
            company="Synthetic Company",
            enabled=False,
        ),
        source["revision"],
        path,
    )

    assert client.get(
        ENDPOINT, params={"id": job["id"]},
    ).status_code == 404


def test_matching_busy(intelligence):
    client, _, _, job = intelligence

    assert api.MATCH_SLOT.acquire(blocking=False)

    try:
        assert client.get(
            ENDPOINT, params={"id": job["id"]},
        ).status_code == 429

    finally:
        api.MATCH_SLOT.release()

    assert client.get(
        ENDPOINT, params={"id": job["id"]},
    ).status_code == 200


@pytest.mark.parametrize("query", [
    "",
    "?id=invalid",
    "?id=a&id=b",
    "?unknown=1",
])
def test_invalid_query(intelligence, query):
    client, _, _, _ = intelligence

    assert client.get(
        ENDPOINT + query,
    ).status_code == 422


def test_unauthenticated_matching_denied():
    with TestClient(app) as client:
        assert client.get(
            ENDPOINT,
            params={"id": str(uuid4())},
        ).status_code in {401, 403}


def test_foreign_origin_denied(intelligence):
    client, _, _, job = intelligence

    assert client.get(
        ENDPOINT,
        params={"id": job["id"]},
        headers={
            "Origin": "https://example.invalid",
        },
    ).status_code == 403


def test_public_matching_requires_authentication(monkeypatch):
    from aegis.main import app

    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")
    monkeypatch.setenv("AEGIS_GATEWAY_TOKEN", "a" * 64)

    with TestClient(app) as client:
        assert client.get(
            ENDPOINT,
            params={"id": str(uuid4())},
            headers={"x-aegis-gateway-token": "a" * 64},
        ).status_code == 401


def test_local_matching_requires_no_network(
    intelligence, monkeypatch,
):
    import socket

    client, _, _, job = intelligence

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected outbound network request")

    monkeypatch.setattr(
        socket.socket,
        "connect",
        forbidden,
    )

    assert client.get(
        ENDPOINT, params={"id": job["id"]},
    ).status_code == 200
