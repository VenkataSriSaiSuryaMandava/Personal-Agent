import sqlite3

import pytest

from aegis.storage import public_quota
from aegis.storage.access_policy import authorize_storage
from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    path = tmp_path / "visitor.sqlite3"

    with authorize_storage(path):
        initialize_database(path)
        yield path


def test_public_page_limit(database):
    with connect(database) as c:
        size = c.execute(
            "PRAGMA page_size"
        ).fetchone()[0]

        pages = c.execute(
            "PRAGMA max_page_count"
        ).fetchone()[0]

        assert pages * size <= (
            public_quota.PUBLIC_DATABASE_LIMIT
        )


def test_quota_enforced_on_reconnection(database):
    with connect(database) as c:
        first = c.execute(
            "PRAGMA max_page_count"
        ).fetchone()[0]

    with connect(database) as c:
        second = c.execute(
            "PRAGMA max_page_count"
        ).fetchone()[0]

    assert first == second


def test_private_database_not_capped(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv(
        "AEGIS_RUNTIME_MODE", "private",
    )

    path = tmp_path / "private-test.sqlite3"

    initialize_database(path)

    with connect(path) as c:
        size = c.execute(
            "PRAGMA page_size"
        ).fetchone()[0]

        pages = c.execute(
            "PRAGMA max_page_count"
        ).fetchone()[0]

        assert pages * size > (
            public_quota.PUBLIC_DATABASE_LIMIT
        )


def test_write_rejected_at_quota(
    database, monkeypatch,
):
    # Exercise a small synthetic limit rather than
    # allocating a large test database.
    monkeypatch.setattr(
        public_quota,
        "PUBLIC_DATABASE_LIMIT",
        1024 * 1024,
    )

    with connect(database) as c:
        c.execute("""
            CREATE TABLE quota_test (
                payload BLOB NOT NULL
            )
        """)

    with pytest.raises(sqlite3.OperationalError):
        with connect(database) as c:
            c.execute("""
                INSERT INTO quota_test(payload)
                VALUES (zeroblob(2097152))
            """)

    with connect(database) as c:
        assert c.execute(
            "SELECT COUNT(*) FROM quota_test"
        ).fetchone()[0] == 0

        assert c.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"

        assert not c.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()


def test_existing_oversized_database_denied(
    database, monkeypatch,
):
    monkeypatch.setattr(
        public_quota,
        "PUBLIC_DATABASE_LIMIT",
        4096,
    )

    with pytest.raises(OSError):
        with connect(database):
            pytest.fail("Oversized database accepted")


def test_original_schema_preserved(database):
    with connect(database) as c:
        assert c.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 9
