import hashlib
import sqlite3
from uuid import uuid4

import pytest

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database
from aegis.storage.backup import create_backup


CAREER_TABLES = (
    "career_audit_events",
    "resume_versions",
    "career_profiles",
)


def test_career_schema(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    with connect(path) as c:
        assert c.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 8

        tables = {
            row[0]
            for row in c.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table'"
            )
        }

        assert set(CAREER_TABLES).issubset(tables)
        assert not c.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()


def test_v6_migration_preserves_existing_data(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with connect(path) as c:
        for table in (
            "job_application_links",
            "job_listings",
            "job_sources",
        ):
            c.execute("DROP TABLE " + table)

        for table in CAREER_TABLES:
            c.execute("DROP TABLE " + table)

        c.execute("PRAGMA user_version = 6")

        before = [
            tuple(row)
            for row in c.execute("SELECT * FROM users")
        ]

        settings = [
            tuple(row)
            for row in c.execute(
                "SELECT * FROM application_settings"
            )
        ]

    initialize_database(path)
    initialize_database(path)

    with connect(path) as c:
        assert c.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 8

        assert [
            tuple(row)
            for row in c.execute("SELECT * FROM users")
        ] == before

        assert [
            tuple(row)
            for row in c.execute(
                "SELECT * FROM application_settings"
            )
        ] == settings

        assert c.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"

        assert not c.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()


def insert_resume(c, active=0, owner=1, size=None):
    data = b"Synthetic resume document"

    identifier = str(uuid4())

    c.execute("""
        INSERT INTO resume_versions (
            id, user_id, title, media_type,
            document, size_bytes, sha256,
            extracted_text, is_active,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
    """, (
        identifier,
        owner,
        "Synthetic resume",
        "text/plain",
        data,
        len(data) if size is None else size,
        hashlib.sha256(data).hexdigest(),
        data.decode(),
        active,
    ))

    return identifier, data


def test_resume_single_active_version(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with connect(path) as c:
        insert_resume(c, active=1)

        with pytest.raises(sqlite3.IntegrityError):
            insert_resume(c, active=1)

        insert_resume(c, active=0)

        assert c.execute(
            "SELECT COUNT(*) FROM resume_versions"
        ).fetchone()[0] == 2


def test_resume_size_constraint(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with pytest.raises(sqlite3.IntegrityError):
        with connect(path) as c:
            insert_resume(c, size=1)


def test_resume_requires_owner(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with pytest.raises(sqlite3.IntegrityError):
        with connect(path) as c:
            insert_resume(c, owner=2)


def test_resume_backup_preserves_document(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with connect(path) as c:
        identifier, original = insert_resume(c)

    backup = create_backup(
        path,
        path.parent / "backups" / "career-test.sqlite3",
    )

    with connect(backup) as c:
        row = c.execute(
            "SELECT document FROM resume_versions "
            "WHERE id = ?",
            (identifier,),
        ).fetchone()

        assert row[0] == original

        assert c.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"
