from aegis.schemas.workspaces import WorkspaceRecord
from aegis.storage.database import connect
from aegis.storage.workspaces import (
    create_record,
    workspace_summary,
)


BASE = "/api/v1/workspaces/summary"


def test_summary_metrics(authenticated_environment):
    client, _, _, path, _ = authenticated_environment

    record = WorkspaceRecord(
        title="Synthetic memory",
        status="active",
        notes="Synthetic Unicode content: café",
    )

    create_record(1, "memory", record, path)

    create_record(
        1,
        "tasks",
        WorkspaceRecord(
            title="Synthetic task",
            status="todo",
        ),
        path,
    )

    response = client.get(BASE)
    assert response.status_code == 200

    data = response.json()

    assert data["counts"]["memory"] == 1
    assert data["statuses"]["memory"]["active"] == 1
    assert data["statuses"]["tasks"]["todo"] == 1
    assert data["statuses"]["tasks"]["completed"] == 0

    with connect(path) as connection:
        expected = connection.execute("""
            SELECT length(CAST(payload AS BLOB))
            FROM workspace_records
            WHERE workspace = 'memory'
        """).fetchone()[0]

    assert data["storage"]["memory_payload_bytes"] == expected
    assert data["storage"]["database_page_bytes"] > 0
    assert data["storage"]["conversation_count"] == 0

    assert "Synthetic memory" not in str(data)
    assert "Synthetic Unicode content" not in str(data)


def test_summary_owner_scope(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    create_record(
        1,
        "memory",
        WorkspaceRecord(
            title="Synthetic memory",
            status="active",
        ),
        path,
    )

    result = workspace_summary(2, path)

    assert result["counts"]["memory"] == 0
    assert result["storage"]["memory_payload_bytes"] == 0
    assert result["storage"]["conversation_count"] == 0


def test_summary_rejects_unknown_query(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    assert client.get(
        BASE + "?user_id=2"
    ).status_code == 422


def test_summary_revoked_session(authenticated_environment):
    client, service, token, _, _ = authenticated_environment

    service.logout(token)

    assert client.get(BASE).status_code == 401
