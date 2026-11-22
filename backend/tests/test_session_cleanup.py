import pytest

from aegis.security.authentication import (
    AuthenticationService,
    AuthenticationDenied,
)

from aegis.security.sessions import (
    SessionManager,
    IDLE_TIMEOUT,
    SESSION_DURATION,
    hash_token,
)

from aegis.security.owner import create_owner
from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


USERNAME = "test-owner"
PASSWORD = "Synthetic owner password 2026!"


@pytest.fixture
def environment(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "sessions.sqlite3"

    initialize_database(path)

    create_owner(USERNAME, PASSWORD, path)

    now = [100000]

    manager = SessionManager(
        path,
        clock=lambda: now[0],
    )

    return manager, path, now


def session_count(path):

    with connect(path) as connection:

        return connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0]


def test_empty_cleanup(environment):

    manager, _, _ = environment

    assert manager.cleanup_expired_sessions() == 0


def test_expired_session_removed(environment):

    manager, path, now = environment

    manager.create_session(1)

    now[0] += SESSION_DURATION

    assert manager.cleanup_expired_sessions() == 1
    assert session_count(path) == 0


def test_idle_session_removed(environment):

    manager, path, now = environment

    manager.create_session(1)

    now[0] += IDLE_TIMEOUT

    assert manager.cleanup_expired_sessions() == 1
    assert session_count(path) == 0


def test_revoked_session_removed(environment):

    manager, path, _ = environment

    token = manager.create_session(1)

    manager.revoke_session(token)

    assert manager.cleanup_expired_sessions() == 1
    assert session_count(path) == 0


def test_active_session_preserved(environment):

    manager, path, now = environment

    token = manager.create_session(1)

    now[0] += 60

    assert manager.cleanup_expired_sessions() == 0
    assert manager.validate_session(token) == 1
    assert session_count(path) == 1


def test_mixed_session_cleanup(environment):

    manager, path, now = environment

    manager.create_session(1)

    now[0] += IDLE_TIMEOUT

    revoked = manager.create_session(1)
    active = manager.create_session(1)

    manager.revoke_session(revoked)

    assert manager.cleanup_expired_sessions() == 2

    assert session_count(path) == 1

    assert manager.validate_session(active) == 1


def test_cleanup_is_idempotent(environment):

    manager, _, _ = environment

    token = manager.create_session(1)

    manager.revoke_session(token)

    assert manager.cleanup_expired_sessions() == 1
    assert manager.cleanup_expired_sessions() == 0


def test_login_automatically_cleans_sessions(
    environment,
):

    manager, path, now = environment

    expired = manager.create_session(1)

    now[0] += IDLE_TIMEOUT

    service = AuthenticationService(
        path,
        clock=lambda: now[0],
    )

    token = service.login(USERNAME, PASSWORD)

    assert service.authenticate(token) == 1
    assert session_count(path) == 1

    with pytest.raises(AuthenticationDenied):

        service.authenticate(expired)


def test_cleanup_preserves_recent_activity(
    environment,
):

    manager, path, now = environment

    token = manager.create_session(1)

    now[0] += IDLE_TIMEOUT - 1

    manager.validate_session(token)

    now[0] += 10

    assert manager.cleanup_expired_sessions() == 0
    assert session_count(path) == 1

    with connect(path) as connection:

        row = connection.execute("""
            SELECT token_hash
            FROM auth_sessions
        """).fetchone()

        assert row["token_hash"] == hash_token(token)
