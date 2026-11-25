from concurrent.futures import ThreadPoolExecutor

import pytest

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from aegis.security.gateway import GatewayDenied
from aegis.security.public_sessions import PublicSessionStore
from aegis.security.request_storage import (
    database_context,
    request_database,
)
from aegis.security.runtime_controls import RuntimeControls
from aegis.storage.database import DATABASE_PATH


def test_private_database_preserved(monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "private")

    assert request_database(DATABASE_PATH) == DATABASE_PATH


def test_private_ignores_public_context(monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "private")

    with database_context(tmp_path / "visitor.sqlite3"):
        assert request_database(DATABASE_PATH) == DATABASE_PATH


def test_public_cannot_fall_back_to_private(monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    with pytest.raises(HTTPException) as error:
        request_database(DATABASE_PATH)

    assert error.value.status_code == 401


def test_public_context_restored(monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    path = tmp_path / "visitor.sqlite3"

    with database_context(path):
        assert request_database(DATABASE_PATH) == path

    with pytest.raises(HTTPException):
        request_database(DATABASE_PATH)


def test_nested_context_restored(monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    a = tmp_path / "first.sqlite3"
    b = tmp_path / "second.sqlite3"

    with database_context(a):
        with database_context(b):
            assert request_database(DATABASE_PATH) == b

        assert request_database(DATABASE_PATH) == a


def test_context_restored_after_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    with pytest.raises(RuntimeError):
        with database_context(tmp_path / "visitor.sqlite3"):
            raise RuntimeError("Synthetic test failure")

    with pytest.raises(HTTPException):
        request_database(DATABASE_PATH)


def test_concurrent_visitors_isolated(monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    store = PublicSessionStore(capacity=2)

    try:
        tokens = [store.create(), store.create()]

        def operation(token):
            with store.lease(token) as path:
                with database_context(path):
                    assert request_database(DATABASE_PATH) == path
                    return path

        with ThreadPoolExecutor(max_workers=2) as pool:
            paths = list(pool.map(operation, tokens))

        assert paths[0] != paths[1]

        with pytest.raises(HTTPException):
            request_database(DATABASE_PATH)

    finally:
        store.close()


def test_context_propagates_to_worker(monkeypatch, tmp_path):
    import asyncio

    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    path = tmp_path / "visitor.sqlite3"

    async def operation():
        with database_context(path):
            result = await run_in_threadpool(
                request_database,
                DATABASE_PATH,
            )

            assert result == path

    asyncio.run(operation())


def test_internal_cloud_gate_denies_public(monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")
    monkeypatch.setenv("AEGIS_AI_ENABLED", "1")
    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")

    with pytest.raises(GatewayDenied):
        RuntimeControls().require_cloud()
