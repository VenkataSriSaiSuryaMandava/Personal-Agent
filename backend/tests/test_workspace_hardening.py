from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from aegis.schemas.workspaces import WorkspaceRecord

from aegis.security.sessions import (
    IDLE_TIMEOUT,
    SESSION_DURATION,
)

from aegis.storage.backup import create_backup
from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database

from aegis.storage.workspaces import (
    RecordConflict,
    create_record,
    update_record,
    delete_record,
    list_records,
    list_page,
    list_audit_events,
)


BASE = "/api/v1/workspaces/tasks"


def sample(title="Synthetic record"):
    return WorkspaceRecord(
        title=title,
        status="todo",
        notes="Synthetic private notes",
    )


def test_audit_lifecycle(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    record = create_record(
        1, "tasks", sample(), path
    )

    identifier = record["id"]

    update_record(
        1, "tasks", identifier,
        sample("Updated record"), 1, path,
    )

    delete_record(
        1, "tasks", identifier, 2, path
    )

    events = list_audit_events(1, path=path)

    assert [
        event["event_type"] for event in events
    ] == ["deleted", "updated", "created"]

    assert [
        event["revision"] for event in events
    ] == [2, 2, 1]

    assert all(
        event["record_id"] == identifier
        for event in events
    )

    assert all(
        set(event) == {
            "id", "workspace", "record_id",
            "event_type", "revision", "created_at",
        }
        for event in events
    )

    assert "Synthetic private notes" not in str(events)
    assert list_records(1, "tasks", path=path) == []


def test_failed_mutations_do_not_create_audit_events(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    record = create_record(
        1, "tasks", sample(), path
    )

    with pytest.raises(RecordConflict):
        update_record(
            1, "tasks", record["id"],
            sample(), 2, path,
        )

    with pytest.raises(RecordConflict):
        delete_record(
            1, "tasks", record["id"], 2, path
        )

    assert len(
        list_audit_events(1, path=path)
    ) == 1


def test_audit_isolation(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    create_record(
        1, "tasks", sample(), path
    )

    assert list_audit_events(2, path=path) == []


def test_audit_and_record_rollback_together(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with pytest.raises(RuntimeError):
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")

            connection.execute("""
                INSERT INTO workspace_records (
                    id, user_id, workspace,
                    payload, revision,
                    created_at, updated_at
                )
                VALUES (?, 1, 'tasks', ?, 1, 1, 1)
            """, (
                "00000000-0000-0000-0000-000000000001",
                sample().model_dump_json(),
            ))

            raise RuntimeError("Synthetic rollback")

    assert list_records(1, "tasks", path=path) == []
    assert list_audit_events(1, path=path) == []


def test_concurrent_updates_preserve_revision(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    record = create_record(
        1, "tasks", sample(), path
    )

    barrier = Barrier(2)

    def change(title):
        barrier.wait(timeout=5)

        try:
            update_record(
                1, "tasks", record["id"],
                sample(title), 1, path,
            )
            return "saved"

        except RecordConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(change, ["First", "Second"])
        )

    assert sorted(results) == [
        "conflict", "saved"
    ]

    current = list_records(
        1, "tasks", path=path
    )

    assert current[0]["revision"] == 2

    assert len(
        list_audit_events(1, path=path)
    ) == 2


def test_exact_page_boundary(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    for index in range(4):
        create_record(
            1, "tasks",
            sample(f"Task {index}"), path,
        )

    first = list_page(
        1, "tasks", 2, 0, path
    )

    second = list_page(
        1, "tasks", 2, 2, path
    )

    assert len(first["records"]) == 2
    assert first["next_offset"] == 2

    assert len(second["records"]) == 2
    assert second["next_offset"] is None

    assert not (
        {r["id"] for r in first["records"]}
        & {r["id"] for r in second["records"]}
    )


def test_api_exact_page_boundary(
    authenticated_environment,
):
    client, _, _, _, _ = authenticated_environment

    for index in range(2):
        assert client.post(
            BASE,
            json=sample(
                f"Task {index}"
            ).model_dump(),
        ).status_code == 200

    response = client.get(BASE + "?limit=2")

    assert response.status_code == 200
    assert response.json()["next_offset"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "Invalid\x00title"),
        ("title", "Invalid\nTitle"),
        ("notes", "Invalid\x01notes"),
        ("detail", "Invalid\x7ftext"),
        ("reference", "Invalid\x00reference"),
        ("scheduled_at", "0001-01-01T00:00:00+01:00"),
        ("scheduled_at", "2027-01-01T12:00:00"),
    ],
)
def test_invalid_record_text(
    authenticated_environment, field, value,
):
    client, _, _, path, _ = authenticated_environment

    data = sample().model_dump()
    data[field] = value

    response = client.post(BASE, json=data)

    assert response.status_code == 422

    assert list_audit_events(1, path=path) == []


def test_invalid_unicode_surrogate(
    authenticated_environment,
):
    client, _, _, _, _ = authenticated_environment

    response = client.post(
        BASE,
        content=(
            b'{"title":"\\ud800","status":"todo"}'
        ),
        headers={
            "Content-Type": "application/json"
        },
    )

    assert response.status_code == 422


def test_normalize_timezone(
    authenticated_environment,
):
    client, _, _, _, _ = authenticated_environment

    response = client.post(
        "/api/v1/workspaces/calendar",
        json={
            "title": "Synthetic event",
            "status": "planned",
            "scheduled_at":
                "2027-01-01T12:00:00-08:00",
        },
    )

    assert response.status_code == 200

    assert response.json()["scheduled_at"] == (
        "2027-01-01T20:00:00+00:00"
    )


@pytest.mark.parametrize(
    "condition",
    ["idle", "expired", "revoked", "inactive"],
)
def test_invalid_sessions_cannot_mutate(
    authenticated_environment, condition,
):
    client, service, token, path, now = (
        authenticated_environment
    )

    if condition == "idle":
        now[0] += IDLE_TIMEOUT

    elif condition == "expired":
        now[0] += SESSION_DURATION

    elif condition == "revoked":
        service.logout(token)

    else:
        with connect(path) as connection:
            connection.execute("""
                UPDATE users
                SET is_active = 0
                WHERE id = 1
            """)

    assert client.get(BASE).status_code == 401

    assert client.post(
        BASE,
        json=sample().model_dump(),
    ).status_code == 401

    assert list_records(
        1, "tasks", path=path
    ) == []

    assert list_audit_events(
        1, path=path
    ) == []


def test_corrupted_record_returns_safe_error(
    authenticated_environment,
):
    client, _, _, path, _ = authenticated_environment

    record = create_record(
        1, "tasks", sample(), path
    )

    with connect(path) as connection:
        connection.execute("""
            UPDATE workspace_records
            SET payload = ?
            WHERE id = ?
        """, (
            "invalid-json",
            record["id"],
        ))

    response = client.get(BASE)

    assert response.status_code == 503

    assert response.json()["detail"] == (
        "Workspace storage unavailable"
    )


def test_v5_to_v6_preserves_records(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    original = create_record(
        1, "tasks", sample(), path
    )

    # Reconstruct schema v5 in an isolated test database.
    with connect(path) as connection:
        connection.execute("DROP TABLE career_audit_events")
        connection.execute("DROP TABLE resume_versions")
        connection.execute("DROP TABLE career_profiles")
        for trigger in (
            "workspace_audit_insert",
            "workspace_audit_update",
            "workspace_audit_delete",
        ):
            connection.execute(
                "DROP TRIGGER " + trigger
            )

        connection.execute(
            "DROP TABLE workspace_audit_events"
        )

        connection.execute(
            "PRAGMA user_version = 5"
        )

    initialize_database(path)
    initialize_database(path)

    assert list_records(
        1, "tasks", path=path
    ) == [original]

    # Do not fabricate historical audit events.
    assert list_audit_events(
        1, path=path
    ) == []

    with connect(path) as connection:
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 7

        assert connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"

        assert not connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()


def test_verified_backup_recovery(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    original = create_record(
        1, "tasks", sample(), path
    )

    backup = create_backup(
        path,
        path.parent / "backups" / "recovery.sqlite3",
    )

    delete_record(
        1, "tasks", original["id"], 1, path
    )

    assert list_records(
        1, "tasks", path=path
    ) == []

    assert list_records(
        1, "tasks", path=backup
    ) == [original]

    assert len(
        list_audit_events(1, path=backup)
    ) == 1

    with connect(backup) as connection:
        assert connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"

        assert not connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()


def test_audit_failure_blocks_mutation(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with connect(path) as connection:
        connection.execute("""
            CREATE TRIGGER synthetic_audit_failure
            BEFORE INSERT ON workspace_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'Synthetic failure');
            END
        """)

    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        create_record(
            1, "tasks", sample(), path
        )

    assert list_records(
        1, "tasks", path=path
    ) == []


def test_approval_does_not_modify_settings(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    from aegis.storage.settings import load_settings

    before = load_settings(path)

    create_record(
        1,
        "approvals",
        WorkspaceRecord(
            title="Synthetic action",
            status="approved",
        ),
        path,
    )

    assert load_settings(path) == before
