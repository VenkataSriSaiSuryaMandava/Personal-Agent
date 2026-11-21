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

    return directory / "test.sqlite3"


def test_database_initialization(database_path):

    initialize_database(database_path)

    assert database_path.exists()

    with connect(database_path) as connection:

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        assert version == SCHEMA_VERSION


def test_required_tables(database_path):

    initialize_database(database_path)

    with connect(database_path) as connection:

        rows = connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
        """).fetchall()

        tables = {row["name"] for row in rows}

        assert "app_metadata" in tables
        assert "api_usage" in tables


def test_database_permissions(database_path):

    initialize_database(database_path)

    assert database_path.stat().st_mode & 0o777 == 0o600


def test_initialization_is_idempotent(database_path):

    initialize_database(database_path)
    initialize_database(database_path)

    with connect(database_path) as connection:

        count = connection.execute("""
            SELECT COUNT(*)
            FROM app_metadata
            WHERE key = 'application'
        """).fetchone()[0]

        assert count == 1


def test_transaction_commit(database_path):

    initialize_database(database_path)

    with connect(database_path) as connection:

        connection.execute(
            "INSERT INTO app_metadata VALUES (?, ?)",
            ("test", "committed"),
        )

    with connect(database_path) as connection:

        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?",
            ("test",),
        ).fetchone()

        assert row["value"] == "committed"


def test_transaction_rollback(database_path):

    initialize_database(database_path)

    with pytest.raises(RuntimeError):

        with connect(database_path) as connection:

            connection.execute(
                "INSERT INTO app_metadata VALUES (?, ?)",
                ("rollback", "test"),
            )

            raise RuntimeError("Simulated failure")

    with connect(database_path) as connection:

        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?",
            ("rollback",),
        ).fetchone()

        assert row is None


def test_unsupported_schema(database_path):

    initialize_database(database_path)

    with connect(database_path) as connection:

        connection.execute("PRAGMA user_version = 999")

    with pytest.raises(RuntimeError):

        initialize_database(database_path)


def test_insecure_permissions_rejected(database_path):

    initialize_database(database_path)

    database_path.chmod(0o644)

    with pytest.raises(PermissionError):

        with connect(database_path):
            pass


def test_foreign_keys_enabled(database_path):

    initialize_database(database_path)

    with connect(database_path) as connection:

        enabled = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        assert enabled == 1


def test_database_symlink_rejected(database_path):

    target = database_path.parent / "target.sqlite3"

    initialize_database(target)

    database_path.symlink_to(target)

    with pytest.raises(PermissionError):

        with connect(database_path):
            pass


def test_insecure_directory_rejected(database_path):

    database_path.parent.chmod(0o755)

    with pytest.raises(PermissionError):

        initialize_database(database_path)
