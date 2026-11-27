"""Persistent local workflow regression tests."""

import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from aegis.schemas.workflows import WorkflowCreate
from aegis.services.agents.permissions import (
    CapabilityDenied,
    authorize_local_capability,
)
from aegis.services.agents.registry import resolve_capability
from aegis.services.company_intelligence import (
    get_company_intelligence,
)
from aegis.services.agents.execution import execute_workflow
from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database
from aegis.storage import workflows as storage


@pytest.fixture
def workflow_database(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "private")
    monkeypatch.setenv("AEGIS_PUBLIC_DEMO", "0")
    monkeypatch.setenv("AEGIS_EMERGENCY_STOP", "0")

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "workflow-test.sqlite3"

    initialize_database(path)

    source_id = str(uuid4())
    now = int(time.time())

    with connect(path) as connection:
        connection.execute("""
            INSERT INTO users (
                id, username, password_hash,
                created_at, is_active
            )
            VALUES (1, 'test-owner', 'test-fixture', ?, 1)
        """, (now,))

        connection.execute("""
            INSERT INTO job_sources (
                id, user_id, provider, board,
                company, enabled,
                created_at, updated_at
            )
            VALUES (
                ?, 1, 'greenhouse', 'example',
                'Example Company', 1, ?, ?
            )
        """, (source_id, now, now))

    return path, source_id


def request_for(source_id, key=None):
    return WorkflowCreate(
        workflow_type="company_summary",
        target_id=source_id,
        request_key=key or str(uuid4()),
    )


def create_run(database):
    path, source_id = database

    run = storage.create_workflow(
        1, request_for(source_id), path,
    )

    return path, run


def test_schema_integrity(workflow_database):
    path, _ = workflow_database

    with connect(path) as connection:
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 9

        assert connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"

        assert not connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()


def test_unknown_capability_rejected():
    with pytest.raises(ValueError):
        resolve_capability("unknown.capability")


@pytest.mark.parametrize(
    "stopped,granted",
    [(True, True), (False, False), (True, False)],
)
def test_capability_permissions(stopped, granted):
    with pytest.raises(CapabilityDenied):
        authorize_local_capability(
            "career.company_summary",
            emergency_stop=stopped,
            scoped_grant=granted,
        )


def test_request_deduplication(workflow_database):
    path, source_id = workflow_database
    request = request_for(source_id)

    first = storage.create_workflow(1, request, path)
    second = storage.create_workflow(1, request, path)

    assert first["id"] == second["id"]

    result = storage.list_workflows(1, path)

    assert len(result["records"]) == 1


def test_conflicting_request_key(workflow_database):
    path, source_id = workflow_database
    key = str(uuid4())

    storage.create_workflow(
        1, request_for(source_id, key), path,
    )

    with pytest.raises(storage.WorkflowConflict):
        storage.create_workflow(
            1, request_for(str(uuid4()), key), path,
        )


def test_unknown_target_rejected(workflow_database):
    path, _ = workflow_database

    with pytest.raises(storage.WorkflowNotFound):
        storage.create_workflow(
            1, request_for(str(uuid4())), path,
        )


def test_owner_scope(workflow_database):
    path, run = create_run(workflow_database)

    with pytest.raises(storage.WorkflowNotFound):
        storage.get_workflow(2, run["id"], path)

    assert storage.list_workflows(
        2, path,
    )["records"] == []


def test_concurrent_claim(workflow_database):
    path, run = create_run(workflow_database)

    def claim(_):
        return storage.claim_workflow(
            1, run["id"], path,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(claim, range(8)))

    assert sum(
        claim is not None for claim in claims
    ) == 1

    detail = storage.get_workflow(
        1, run["id"], path,
    )

    assert detail["status"] == "running"
    assert detail["steps"][0]["attempt_count"] == 1


def test_successful_completion(workflow_database):
    path, run = create_run(workflow_database)

    claim = storage.claim_workflow(
        1, run["id"], path,
    )

    storage.finish_workflow(
        1, run["id"],
        claim["id"], claim["lease_token"],
        path,
        output={"result": "completed"},
    )

    detail = storage.get_workflow(
        1, run["id"], path,
    )

    assert detail["status"] == "completed"

    assert detail["steps"][0]["output"] == {
        "result": "completed",
    }

    assert storage.claim_workflow(
        1, run["id"], path,
    ) is None


def test_stale_lease_rejected(workflow_database):
    path, run = create_run(workflow_database)

    claim = storage.claim_workflow(
        1, run["id"], path,
    )

    with pytest.raises(storage.WorkflowLeaseLost):
        storage.finish_workflow(
            1, run["id"], claim["id"],
            str(uuid4()), path,
            output={"invalid": True},
        )


def test_expired_lease_recovery(workflow_database):
    path, run = create_run(workflow_database)

    old = storage.claim_workflow(
        1, run["id"], path,
    )

    with connect(path) as connection:
        connection.execute("""
            UPDATE workflow_steps
            SET lease_expires_at = 0
            WHERE id = ?
        """, (old["id"],))

    new = storage.claim_workflow(
        1, run["id"], path,
    )

    assert new["attempt_count"] == 2
    assert new["lease_token"] != old["lease_token"]

    with pytest.raises(storage.WorkflowLeaseLost):
        storage.finish_workflow(
            1, run["id"], old["id"],
            old["lease_token"], path,
            output={"stale": True},
        )


def test_cancel_queued_workflow(workflow_database):
    path, run = create_run(workflow_database)

    cancelled = storage.cancel_workflow(
        1, run["id"], run["revision"], path,
    )

    assert cancelled["status"] == "cancelled"

    assert storage.claim_workflow(
        1, run["id"], path,
    ) is None


def test_cancel_running_workflow(workflow_database):
    path, run = create_run(workflow_database)

    claim = storage.claim_workflow(
        1, run["id"], path,
    )

    detail = storage.get_workflow(
        1, run["id"], path,
    )

    storage.cancel_workflow(
        1, run["id"], detail["revision"], path,
    )

    storage.finish_workflow(
        1, run["id"],
        claim["id"], claim["lease_token"],
        path,
        output={"discarded": True},
    )

    result = storage.get_workflow(
        1, run["id"], path,
    )

    assert result["status"] == "cancelled"
    assert result["steps"][0]["output"] is None


def test_stale_cancellation_revision(workflow_database):
    path, run = create_run(workflow_database)

    storage.claim_workflow(1, run["id"], path)

    with pytest.raises(storage.WorkflowConflict):
        storage.cancel_workflow(
            1, run["id"], run["revision"], path,
        )


def test_event_cursor(workflow_database):
    path, run = create_run(workflow_database)

    storage.claim_workflow(1, run["id"], path)

    page = storage.list_events(
        1, run["id"], path, limit=1,
    )

    assert page["has_more"]

    second = storage.list_events(
        1, run["id"], path,
        after_id=page["next_cursor"],
    )

    assert second["events"][0]["event_type"] == (
        "workflow.started"
    )


def test_payload_limit():
    with pytest.raises(ValueError):
        storage.encode_payload({
            "content": "x" * 32769,
        })


def test_real_company_execution(workflow_database):
    path, run = create_run(workflow_database)

    def company(user_id, parameters, database):
        return get_company_intelligence(
            user_id,
            str(parameters.source_id),
            database,
        )

    result = execute_workflow(
        1, run["id"], path,
        reauthorize=lambda: None,
        handlers={
            "career.company_summary": company,
        },
    )

    assert result["status"] == "completed"

    output = result["steps"][0]["output"]

    assert output["company"] == "Example Company"
    assert output["open_listings"] == 0
    assert output["identity_verified"] is False


def test_invalid_result_fails_closed(workflow_database):
    path, run = create_run(workflow_database)

    result = execute_workflow(
        1, run["id"], path,
        reauthorize=lambda: None,
        handlers={
            "career.company_summary":
                lambda *_: {"unexpected": True},
        },
    )

    assert result["status"] == "failed"
    assert result["steps"][0]["output"] is None
    assert result["steps"][0]["error_code"] == (
        "invalid_contract"
    )


def test_v8_migration_preserves_all_records(workflow_database):
    path, _ = workflow_database

    with connect(path) as connection:
        connection.execute("DROP TABLE workflow_events")
        connection.execute("DROP TABLE workflow_steps")
        connection.execute("DROP TABLE workflow_runs")
        connection.execute("PRAGMA user_version = 8")

        tables = [
            row[0]
            for row in connection.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
        ]

        before = {
            table: [
                tuple(row)
                for row in connection.execute(
                    'SELECT * FROM "' + table + '"'
                )
            ]
            for table in tables
        }

    initialize_database(path)
    initialize_database(path)

    with connect(path) as connection:
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 9

        for table, records in before.items():
            assert [
                tuple(row)
                for row in connection.execute(
                    'SELECT * FROM "' + table + '"'
                )
            ] == records

        for table in (
            "workflow_runs",
            "workflow_steps",
            "workflow_events",
        ):
            assert connection.execute(
                'SELECT COUNT(*) FROM "' + table + '"'
            ).fetchone()[0] == 0

        assert connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"

        assert not connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()


def test_v9_migration_collision_rolls_back(workflow_database):
    path, _ = workflow_database

    with connect(path) as connection:
        connection.execute("DROP TABLE workflow_events")
        connection.execute("DROP TABLE workflow_steps")

        # Deliberately retain workflow_runs to simulate
        # an inconsistent historical database.
        connection.execute("PRAGMA user_version = 8")

    import sqlite3

    with pytest.raises(sqlite3.OperationalError):
        initialize_database(path)

    with connect(path) as connection:
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 8

        tables = {
            row[0]
            for row in connection.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'table'
            """)
        }

        assert "workflow_runs" in tables
        assert "workflow_steps" not in tables
        assert "workflow_events" not in tables

        assert connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"
