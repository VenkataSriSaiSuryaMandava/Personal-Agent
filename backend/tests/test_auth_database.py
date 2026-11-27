import sqlite3

import pytest

from aegis.storage.database import connect
from aegis.storage.migrations import (
    SCHEMA_VERSION,
    initialize_database,
)


@pytest.fixture
def database_path(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "auth.sqlite3"

    initialize_database(path)

    return path


def create_owner(connection):

    connection.execute("""
        INSERT INTO users (
            id, username, password_hash, created_at
        )
        VALUES (?, ?, ?, ?)
    """, (1, "test-owner", "synthetic-hash", 100000))


def create_session(connection):

    connection.execute("""
        INSERT INTO auth_sessions (
            user_id,
            token_hash,
            created_at,
            expires_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (1, "synthetic-token-hash", 100000, 103600, 100000))


def test_authentication_tables(database_path):

    with connect(database_path) as connection:

        tables = {
            row["name"]
            for row in connection.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
            """)
        }

        assert {
            "users",
            "auth_sessions",
            "login_attempts",
        }.issubset(tables)


def test_version_one_migration_preserves_data(database_path):

    with connect(database_path) as connection:

        connection.execute("DROP TABLE job_application_links")
        connection.execute("DROP TABLE job_listings")
        connection.execute("DROP TABLE job_sources")
        connection.execute("DROP TABLE career_audit_events")
        connection.execute("DROP TABLE resume_versions")
        connection.execute("DROP TABLE career_profiles")
        connection.execute("DROP TABLE workspace_records")
        connection.execute("DROP TABLE workspace_audit_events")
        connection.execute("DROP TABLE conversation_turns")
        connection.execute("DROP TABLE conversations")
        connection.execute("DROP TABLE security_audit_events")
        connection.execute("DROP TABLE application_settings")
        connection.execute("DROP TABLE auth_sessions")
        connection.execute("DROP TABLE login_attempts")
        connection.execute("DROP TABLE users")

        connection.execute("""
            INSERT INTO api_usage (
                provider, created_at
            )
            VALUES (?, ?)
        """, ("gemini", 100000))

        connection.execute("""
            INSERT INTO app_metadata (key, value)
            VALUES (?, ?)
        """, ("migration-test", "preserved"))

        # Remove schema 9 tables from historical test fixture.
        connection.execute("DROP TABLE workflow_events")
        connection.execute("DROP TABLE workflow_steps")
        connection.execute("DROP TABLE workflow_runs")
        connection.execute("PRAGMA user_version = 1")

    initialize_database(database_path)

    with connect(database_path) as connection:

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        usage = connection.execute("""
            SELECT provider, created_at
            FROM api_usage
        """).fetchone()

        metadata = connection.execute("""
            SELECT value
            FROM app_metadata
            WHERE key = 'migration-test'
        """).fetchone()

        assert version == SCHEMA_VERSION
        assert usage["provider"] == "gemini"
        assert usage["created_at"] == 100000
        assert metadata["value"] == "preserved"


def test_owner_creation(database_path):

    with connect(database_path) as connection:

        create_owner(connection)

        owner = connection.execute(
            "SELECT * FROM users WHERE id = 1"
        ).fetchone()

        assert owner["username"] == "test-owner"
        assert owner["is_active"] == 1


def test_second_owner_rejected(database_path):

    with connect(database_path) as connection:

        create_owner(connection)

        with pytest.raises(sqlite3.IntegrityError):

            connection.execute("""
                INSERT INTO users (
                    id, username, password_hash, created_at
                )
                VALUES (?, ?, ?, ?)
            """, (2, "another-owner", "synthetic-hash", 100000))


def test_invalid_owner_status(database_path):

    with connect(database_path) as connection:

        with pytest.raises(sqlite3.IntegrityError):

            connection.execute("""
                INSERT INTO users (
                    id, username, password_hash,
                    created_at, is_active
                )
                VALUES (?, ?, ?, ?, ?)
            """, (1, "test-owner", "synthetic-hash", 100000, 2))


def test_session_creation(database_path):

    with connect(database_path) as connection:

        create_owner(connection)
        create_session(connection)

        session = connection.execute(
            "SELECT * FROM auth_sessions"
        ).fetchone()

        assert session["user_id"] == 1
        assert session["token_hash"] == "synthetic-token-hash"
        assert session["expires_at"] == 103600
        assert session["revoked_at"] is None


def test_duplicate_session_token_rejected(database_path):

    with connect(database_path) as connection:

        create_owner(connection)
        create_session(connection)

        with pytest.raises(sqlite3.IntegrityError):

            create_session(connection)


def test_session_without_owner_rejected(database_path):

    with connect(database_path) as connection:

        with pytest.raises(sqlite3.IntegrityError):

            create_session(connection)


def test_invalid_session_expiration(database_path):

    with connect(database_path) as connection:

        create_owner(connection)

        with pytest.raises(sqlite3.IntegrityError):

            connection.execute("""
                INSERT INTO auth_sessions (
                    user_id,
                    token_hash,
                    created_at,
                    expires_at,
                    last_seen_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (1, "synthetic-token", 100000, 99999, 100000))


def test_owner_deletion_removes_sessions(database_path):

    with connect(database_path) as connection:

        create_owner(connection)
        create_session(connection)

        connection.execute(
            "DELETE FROM users WHERE id = 1"
        )

        count = connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0]

        assert count == 0


def test_login_attempt_recording(database_path):

    with connect(database_path) as connection:

        connection.executemany("""
            INSERT INTO login_attempts (
                attempted_at, successful
            )
            VALUES (?, ?)
        """, [
            (100000, 0),
            (100001, 0),
            (100002, 1),
        ])

        failed = connection.execute("""
            SELECT COUNT(*)
            FROM login_attempts
            WHERE successful = 0
        """).fetchone()[0]

        assert failed == 2


def test_invalid_login_attempt_rejected(database_path):

    with connect(database_path) as connection:

        with pytest.raises(sqlite3.IntegrityError):

            connection.execute("""
                INSERT INTO login_attempts (
                    attempted_at, successful
                )
                VALUES (?, ?)
            """, (100000, 2))


def test_reinitialization_preserves_authentication_data(database_path):

    with connect(database_path) as connection:

        create_owner(connection)
        create_session(connection)

    initialize_database(database_path)

    with connect(database_path) as connection:

        assert connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0] == 1

        assert connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0] == 1
