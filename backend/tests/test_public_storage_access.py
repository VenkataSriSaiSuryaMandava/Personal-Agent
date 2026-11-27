from concurrent.futures import ThreadPoolExecutor

import pytest

from aegis.security.public_sessions import PublicSessionStore
from aegis.security.request_storage import database_context
from aegis.storage.access_policy import authorize_storage
from aegis.storage.database import (
    DATABASE_PATH,
    connect,
    prepare_database,
)
from aegis.storage.migrations import initialize_database


def test_public_default_path_denied(monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    with pytest.raises(PermissionError):
        with connect():
            pytest.fail("Default private database opened")


def test_public_database_creation_requires_authorization(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    path = tmp_path / "unapproved" / "test.sqlite3"

    with pytest.raises(PermissionError):
        prepare_database(path)

    assert not path.parent.exists()


def test_public_explicit_unapproved_path_denied(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    path = tmp_path / "test.sqlite3"

    with pytest.raises(PermissionError):
        with connect(path):
            pytest.fail("Unauthorized database opened")

    assert not path.exists()


def test_public_authorized_database_access(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    path = tmp_path / "visitor.sqlite3"

    with authorize_storage(path):
        initialize_database(path)

        with connect(path) as c:
            assert c.execute(
                "PRAGMA user_version"
            ).fetchone()[0] == 9

        with pytest.raises(PermissionError):
            with connect(DATABASE_PATH):
                pytest.fail("Private database opened")

    with pytest.raises(PermissionError):
        with connect(path):
            pytest.fail("Authorization leaked")


def test_public_request_cannot_open_other_visitor(
    monkeypatch,
):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    store = PublicSessionStore(capacity=2)

    try:
        first = store.create()
        second = store.create()

        with store.lease(first) as a:
            with store.lease(second) as b:
                with database_context(a):
                    with connect(a):
                        pass

                    with pytest.raises(PermissionError):
                        with connect(b):
                            pytest.fail(
                                "Other visitor database opened"
                            )

                with database_context(b):
                    with connect(b):
                        pass

                    with pytest.raises(PermissionError):
                        with connect(a):
                            pytest.fail(
                                "Other visitor database opened"
                            )
    finally:
        store.close()


def test_storage_authorization_restored_after_error(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    path = tmp_path / "visitor.sqlite3"

    with pytest.raises(RuntimeError):
        with authorize_storage(path):
            raise RuntimeError("Synthetic error")

    with pytest.raises(PermissionError):
        with connect(path):
            pytest.fail("Authorization leaked")


def test_concurrent_storage_authorization(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    paths = [
        tmp_path / "a" / "visitor.sqlite3",
        tmp_path / "b" / "visitor.sqlite3",
    ]

    def operation(index):
        own = paths[index]
        other = paths[1 - index]

        with authorize_storage(own):
            initialize_database(own)

            with connect(own):
                pass

            with pytest.raises(PermissionError):
                with connect(other):
                    pytest.fail("Cross-thread storage access")

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(operation, range(2)))


def test_private_storage_behavior_unchanged(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "private")

    path = tmp_path / "private.sqlite3"

    initialize_database(path)

    with connect(path) as c:
        assert c.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"
