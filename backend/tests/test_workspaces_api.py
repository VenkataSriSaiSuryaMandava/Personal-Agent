import pytest

from fastapi.testclient import TestClient

from aegis.main import app
from aegis.schemas.workspaces import STATUSES
from aegis.storage.workspaces import list_records


BASE = "/api/v1/workspaces"
FAKE_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def client(authenticated_environment):
    return authenticated_environment[0]


def payload(workspace):
    result = {
        "title": "Synthetic record",
        "detail": "Synthetic detail",
        "notes": "Synthetic notes",
        "status": STATUSES[workspace][0],
        "priority": "normal",
        "reference": "",
        "scheduled_at": "",
    }

    if workspace == "calendar":
        result["scheduled_at"] = (
            "2027-01-01T12:00:00+00:00"
        )

    return result


@pytest.mark.parametrize(
    "workspace", list(STATUSES)
)
def test_workspace_lifecycle(client, workspace):
    data = payload(workspace)
    base = BASE + "/" + workspace

    response = client.post(base, json=data)

    assert response.status_code == 200

    record = response.json()
    assert record["revision"] == 1

    path = base + "/" + record["id"]

    response = client.get(base)
    assert response.status_code == 200
    assert len(response.json()["records"]) == 1

    data["title"] = "Updated record"

    response = client.patch(
        path,
        json={
            **data,
            "expected_revision": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 2

    assert client.patch(
        path,
        json={
            **data,
            "expected_revision": 1,
        },
    ).status_code == 409

    summary = client.get(BASE + "/summary")

    assert summary.status_code == 200
    assert summary.json()["counts"][workspace] == 1

    assert client.delete(
        path + "?revision=1"
    ).status_code == 409

    assert client.delete(
        path + "?revision=2"
    ).status_code == 200

    assert client.get(base).json()["records"] == []

    assert client.get(
        BASE + "/summary"
    ).json()["counts"][workspace] == 0


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/summary"),
        ("GET", "/tasks"),
        ("POST", "/tasks"),
        ("PATCH", "/tasks/" + FAKE_ID),
        ("DELETE", "/tasks/" + FAKE_ID),
    ],
)
def test_gateway_required(method, path):
    with TestClient(app) as anonymous:
        response = anonymous.request(
            method, BASE + path
        )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/summary"),
        ("GET", "/tasks"),
        ("POST", "/tasks"),
        ("PATCH", "/tasks/" + FAKE_ID),
        ("DELETE", "/tasks/" + FAKE_ID),
    ],
)
def test_owner_session_required(client, method, path):
    with TestClient(
        app,
        headers={
            "x-aegis-gateway-token":
                client.headers["x-aegis-gateway-token"],
        },
    ) as anonymous:

        response = anonymous.request(
            method, BASE + path
        )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        {"title": ""},
        {"title": "   "},
        {"status": "unknown"},
        {"priority": "unknown"},
        {"scheduled_at": "invalid"},
        {"scheduled_at": "2027-01-01T12:00:00"},
        {"notes": "x" * 8001},
        {"unknown": "field"},
        {"user_id": 2},
    ],
)
def test_invalid_record(client, change):
    response = client.post(
        BASE + "/tasks",
        json={
            **payload("tasks"),
            **change,
        },
    )

    assert response.status_code == 422


def test_cross_workspace_isolation(client):
    created = client.post(
        BASE + "/tasks",
        json=payload("tasks"),
    ).json()

    result = client.delete(
        BASE + "/jobs/" + created["id"] +
        "?revision=1"
    )

    assert result.status_code == 404

    assert len(
        client.get(
            BASE + "/tasks"
        ).json()["records"]
    ) == 1


def test_owner_storage_isolation(
    authenticated_environment,
):
    client, _, _, path, _ = (
        authenticated_environment
    )

    assert client.post(
        BASE + "/tasks",
        json=payload("tasks"),
    ).status_code == 200

    assert list_records(
        2, "tasks", path=path
    ) == []


def test_duplicate_keys(client):
    response = client.post(
        BASE + "/tasks",
        content=(
            '{"title":"first",'
            '"title":"second",'
            '"status":"todo"}'
        ),
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422


def test_foreign_origin(client):
    assert client.get(
        BASE + "/tasks",
        headers={
            "Origin": "https://example.invalid",
        },
    ).status_code == 403


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=1&limit=2",
        "offset=-1",
        "unknown=1",
    ],
)
def test_invalid_query(client, query):
    assert client.get(
        BASE + "/tasks?" + query
    ).status_code == 422


def test_pagination(client):
    for index in range(3):
        response = client.post(
            BASE + "/tasks",
            json={
                **payload("tasks"),
                "title": f"Synthetic {index}",
            },
        )

        assert response.status_code == 200

    first = client.get(
        BASE + "/tasks?limit=2"
    ).json()

    second = client.get(
        BASE + "/tasks?limit=2&offset=2"
    ).json()

    assert len(first["records"]) == 2
    assert first["next_offset"] == 2
    assert len(second["records"]) == 1
    assert second["next_offset"] is None


def test_calendar_requires_date(client):
    response = client.post(
        BASE + "/calendar",
        json={
            **payload("calendar"),
            "scheduled_at": "",
        },
    )

    assert response.status_code == 422


def test_approval_is_only_a_record(client):
    response = client.post(
        BASE + "/approvals",
        json={
            **payload("approvals"),
            "status": "approved",
        },
    )

    assert response.status_code == 200
    assert "executed" not in response.json()


def test_oversized_payload(client):
    response = client.post(
        BASE + "/tasks",
        content=b"x" * 65537,
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 413


def test_wrong_content_type(client):
    response = client.post(
        BASE + "/tasks",
        content="synthetic",
        headers={
            "Content-Type": "text/plain",
        },
    )

    assert response.status_code == 415


def test_security_headers(client):
    response = client.get(BASE + "/tasks")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
