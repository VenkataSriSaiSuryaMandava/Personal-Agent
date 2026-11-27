import sqlite3

import pytest

from aegis.schemas.discovery import JobSourceInput

from aegis.services.job_sources import source_endpoint

from aegis.storage import discovery as storage

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database
from aegis.storage.backup import create_backup

from aegis.schemas.workspaces import WorkspaceRecord
from aegis.storage.workspaces import create_record


SOURCE = JobSourceInput(
    provider="greenhouse",
    board="synthetic-company",
    company="Synthetic Company",
)

TABLES = (
    "job_application_links",
    "job_listings",
    "job_sources",
)


@pytest.mark.parametrize("provider,expected", [
    (
        "greenhouse",
        "https://boards-api.greenhouse.io/v1/boards/"
        "synthetic-company/jobs?content=true",
    ),
    (
        "lever",
        "https://api.lever.co/v0/postings/"
        "synthetic-company?mode=json",
    ),
    (
        "ashby",
        "https://api.ashbyhq.com/posting-api/"
        "job-board/synthetic-company",
    ),
])
def test_fixed_provider_endpoints(provider, expected):
    source = JobSourceInput(
        provider=provider,
        board="synthetic-company",
        company="Synthetic Company",
    )

    assert source_endpoint(source) == expected


@pytest.mark.parametrize("board", [
    "",
    "../test",
    "https://example.invalid",
    "test?query=1",
    "test#fragment",
    "test/other",
    "test%2Fother",
    "test@other",
    "test\\other",
    "test\nother",
    " test",
    "a" * 101,
])
def test_invalid_board_rejected(board):
    with pytest.raises(ValueError):
        JobSourceInput(
            provider="greenhouse",
            board=board,
            company="Synthetic Company",
        )


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        JobSourceInput(
            provider="unknown",
            board="example",
            company="Synthetic Company",
        )


def test_source_lifecycle(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    source = storage.create_source(1, SOURCE, path)

    assert source["revision"] == 1
    assert source["last_result"] == "never"
    assert source["enabled"] == 1

    assert len(storage.list_sources(1, path)) == 1

    changed = SOURCE.model_copy(
        update={"enabled": False}
    )

    updated = storage.update_source(
        1, source["id"], changed, 1, path,
    )

    assert updated["revision"] == 2
    assert updated["enabled"] == 0

    with pytest.raises(storage.SourceConflict):
        storage.delete_source(
            1, source["id"], 1, path,
        )

    storage.delete_source(
        1, source["id"], 2, path,
    )

    assert storage.list_sources(1, path) == []


def test_duplicate_source(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    storage.create_source(1, SOURCE, path)

    with pytest.raises(storage.SourceConflict):
        storage.create_source(1, SOURCE, path)


def test_source_owner_isolation(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    source = storage.create_source(1, SOURCE, path)

    assert storage.list_sources(2, path) == []

    with pytest.raises(storage.SourceNotFound):
        storage.get_source(2, source["id"], path)

    with pytest.raises(storage.SourceNotFound):
        storage.delete_source(
            2, source["id"], 1, path,
        )


def test_source_identity_is_immutable(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    source = storage.create_source(1, SOURCE, path)

    changed = SOURCE.model_copy(
        update={"board": "different-company"}
    )

    with pytest.raises(ValueError):
        storage.update_source(
            1, source["id"], changed, 1, path,
        )


def test_source_limit(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    for index in range(100):
        storage.create_source(
            1,
            SOURCE.model_copy(
                update={"board": f"company-{index}"}
            ),
            path,
        )

    with pytest.raises(storage.SourceConflict):
        storage.create_source(1, SOURCE, path)


def test_schema_v7_migration(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with connect(path) as c:
        for table in TABLES:
            c.execute("DROP TABLE " + table)

        # Remove schema 9 tables from historical test fixture.
        c.execute("DROP TABLE workflow_events")
        c.execute("DROP TABLE workflow_steps")
        c.execute("DROP TABLE workflow_runs")
        c.execute("PRAGMA user_version = 7")

        existing_tables = [
            row[0] for row in c.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                AND name NOT LIKE 'sqlite_%'
            """)
        ]

        before = {
            table: [
                tuple(row) for row in c.execute(
                    "SELECT * FROM " + table
                )
            ]
            for table in existing_tables
        }

    initialize_database(path)
    initialize_database(path)

    with connect(path) as c:
        assert c.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 9

        for table, records in before.items():
            assert [
                tuple(row) for row in c.execute(
                    "SELECT * FROM " + table
                )
            ] == records

        assert c.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"

        assert not c.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()


def test_migration_rollback(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with connect(path) as c:
        c.execute("DROP TABLE job_application_links")
        c.execute("DROP TABLE job_listings")

        # Retain job_sources to trigger a schema collision.
        # Remove schema 9 tables from historical test fixture.
        c.execute("DROP TABLE workflow_events")
        c.execute("DROP TABLE workflow_steps")
        c.execute("DROP TABLE workflow_runs")
        c.execute("PRAGMA user_version = 7")

    with pytest.raises(sqlite3.OperationalError):
        initialize_database(path)

    with connect(path) as c:
        assert c.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 7

        assert c.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE name = 'job_listings'
        """).fetchone()[0] == 0

        assert c.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"


def test_source_backup(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    source = storage.create_source(1, SOURCE, path)

    backup = create_backup(
        path,
        path.parent / "backups" / "discovery-test.sqlite3",
    )

    assert storage.get_source(
        1, source["id"], backup,
    ) == source


def test_application_links_preserve_pipeline(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    source = storage.create_source(1, SOURCE, path)

    application = create_record(
        1,
        "jobs",
        WorkspaceRecord(
            title="Synthetic developer",
            status="saved",
            detail="Synthetic Company",
        ),
        path,
    )

    with connect(path) as c:
        c.execute("""
            INSERT INTO job_application_links (
                user_id, application_id, provider,
                board, external_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            1, application["id"],
            SOURCE.provider, SOURCE.board,
            "synthetic-job", 1,
        ))

    storage.delete_source(
        1, source["id"], 1, path,
    )

    with connect(path) as c:
        assert c.execute("""
            SELECT COUNT(*) FROM workspace_records
            WHERE id = ?
        """, (application["id"],)).fetchone()[0] == 1

        assert c.execute("""
            SELECT COUNT(*) FROM job_application_links
            WHERE application_id = ?
        """, (application["id"],)).fetchone()[0] == 1


def test_non_job_application_link_rejected(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    task = create_record(
        1,
        "tasks",
        WorkspaceRecord(
            title="Synthetic task",
            status="todo",
        ),
        path,
    )

    with pytest.raises(sqlite3.IntegrityError):
        with connect(path) as c:
            c.execute("""
                INSERT INTO job_application_links (
                    user_id, application_id, provider,
                    board, external_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                1, task["id"], "lever",
                "synthetic-company",
                "synthetic-job", 1,
            ))
