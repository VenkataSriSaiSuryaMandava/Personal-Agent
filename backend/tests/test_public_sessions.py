import secrets
import stat

import pytest

from aegis.schemas.career import CareerProfile
from aegis.schemas.workspaces import WorkspaceRecord
from aegis.security.public_sessions import (
    MAX_PUBLIC_SESSIONS,
    PublicCapacityExceeded,
    PublicSessionStore,
)
from aegis.security.sessions import (
    IDLE_TIMEOUT,
    SESSION_DURATION,
    SessionDenied,
    SessionManager,
    hash_token,
)
from aegis.services.settings import SettingsService
from aegis.storage import career, workspaces
from aegis.storage.database import DATABASE_PATH, connect
from aegis.storage.migrations import SCHEMA_VERSION


@pytest.fixture
def environment():
    now = [100000]

    store = PublicSessionStore(
        capacity=2,
        clock=lambda: now[0],
    )

    try:
        yield store, now

    finally:
        store.close()


def test_same_schema_and_secure_permissions(environment):
    store, _ = environment

    token = store.create()

    with store.lease(token) as path:
        assert path != DATABASE_PATH

        assert stat.S_IMODE(
            path.stat().st_mode
        ) == 0o600

        assert stat.S_IMODE(
            path.parent.stat().st_mode
        ) == 0o700

        with connect(path) as c:
            assert c.execute(
                "PRAGMA user_version"
            ).fetchone()[0] == SCHEMA_VERSION

            assert c.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0] == "ok"

            assert not c.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()


def test_visitors_use_separate_databases(environment):
    store, _ = environment

    first = store.create()
    second = store.create()

    with store.lease(first) as a:
        with store.lease(second) as b:
            assert a != b

            career.save_profile(
                1,
                CareerProfile(
                    full_name="Synthetic visitor A",
                    skills=["Python"],
                ),
                0,
                a,
            )

            assert career.get_profile(
                1, a,
            )["revision"] == 1

            assert career.get_profile(
                1, b,
            )["revision"] == 0


def test_real_workspace_storage_isolated(environment):
    store, _ = environment

    first = store.create()
    second = store.create()

    with store.lease(first) as a:
        with store.lease(second) as b:
            workspaces.create_record(
                1,
                "tasks",
                WorkspaceRecord(
                    title="Synthetic private task",
                    status="todo",
                ),
                a,
            )

            with connect(a) as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM workspace_records"
                ).fetchone()[0] == 1

            with connect(b) as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM workspace_records"
                ).fetchone()[0] == 0


def test_application_settings_isolated(environment):
    store, _ = environment

    first = store.create()
    second = store.create()

    with store.lease(first) as a:
        with store.lease(second) as b:
            settings_a = SettingsService(a)
            settings_b = SettingsService(b)

            original_b = settings_b.get()

            settings_a.update(
                {"theme": "dark"},
                settings_a.get().revision,
            )

            assert settings_a.get().settings.theme == "dark"
            assert settings_b.get() == original_b


def test_tokens_cannot_cross_databases(environment):
    store, now = environment

    first = store.create()
    second = store.create()

    with store.lease(second) as path:
        with pytest.raises(SessionDenied):
            SessionManager(
                path, lambda: now[0],
            ).validate_session(first)


def test_session_registry_stores_only_token_hash(environment):
    store, _ = environment

    token = store.create()

    assert token not in store._entries
    assert hash_token(token) in store._entries


def test_capacity_limit(environment):
    store, _ = environment

    store.create()
    store.create()

    with pytest.raises(PublicCapacityExceeded):
        store.create()


def test_idle_timeout_and_cleanup(environment):
    store, now = environment

    token = store.create()

    with store.lease(token) as path:
        assert path.exists()

    now[0] += IDLE_TIMEOUT

    assert store.cleanup_expired() == 1
    assert not path.exists()

    with pytest.raises(SessionDenied):
        with store.lease(token):
            pytest.fail("Expired session accepted")


def test_activity_extends_idle_timeout(environment):
    store, now = environment

    token = store.create()

    now[0] += IDLE_TIMEOUT - 1

    with store.lease(token):
        pass

    now[0] += IDLE_TIMEOUT - 1

    with store.lease(token):
        pass


def test_absolute_session_timeout(environment):
    store, now = environment

    token = store.create()

    for _ in range(
        SESSION_DURATION // (IDLE_TIMEOUT - 1)
    ):
        now[0] += IDLE_TIMEOUT - 1

        with store.lease(token):
            pass

    now[0] = 100000 + SESSION_DURATION

    with pytest.raises(SessionDenied):
        with store.lease(token):
            pytest.fail("Expired session accepted")


def test_revoked_session_removed(environment):
    store, _ = environment

    token = store.create()

    with store.lease(token) as path:
        pass

    store.revoke(token)

    assert not path.exists()

    with pytest.raises(SessionDenied):
        with store.lease(token):
            pytest.fail("Revoked session accepted")


def test_cleanup_waits_for_inflight_request(environment):
    store, now = environment

    token = store.create()

    with store.lease(token) as path:
        now[0] += IDLE_TIMEOUT

        assert store.cleanup_expired() == 0
        assert path.exists()

        with pytest.raises(SessionDenied):
            with store.lease(token):
                pytest.fail("Expired session accepted")

    assert not path.exists()


def test_logout_waits_for_inflight_request(environment):
    store, _ = environment

    token = store.create()

    with store.lease(token) as path:
        store.revoke(token)
        assert path.exists()

    assert not path.exists()


def test_capacity_recovered_after_expiration(environment):
    store, now = environment

    store.create()
    store.create()

    now[0] += IDLE_TIMEOUT

    assert store.cleanup_expired() == 2

    token = store.create()

    with store.lease(token) as path:
        assert path.exists()


@pytest.mark.parametrize("token", [
    "",
    "../aegis.sqlite3",
    "invalid",
    None,
    secrets.token_urlsafe(32),
])
def test_invalid_or_unknown_session(environment, token):
    store, _ = environment

    with pytest.raises(SessionDenied):
        with store.lease(token):
            pytest.fail("Unknown session accepted")


@pytest.mark.parametrize("capacity", [
    0, -1, True, MAX_PUBLIC_SESSIONS + 1,
])
def test_invalid_capacity(capacity):
    with pytest.raises(ValueError):
        PublicSessionStore(capacity=capacity)


def test_shutdown_cleans_temporary_databases(environment):
    store, _ = environment

    token = store.create()

    with store.lease(token) as path:
        pass

    store.close()

    assert not path.exists()
