import pytest

from aegis.security.owner import create_owner

from aegis.security.sessions import (
    SessionManager,
    SessionDenied,
    SESSION_DURATION,
    IDLE_TIMEOUT,
    hash_token,
    valid_token_format,
)

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


@pytest.fixture
def database_path(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "sessions.sqlite3"

    initialize_database(path)

    create_owner(
        "test-owner",
        "Synthetic owner password 2026!",
        path,
    )

    return path


@pytest.fixture
def environment(database_path):

    now = [100000]

    manager = SessionManager(
        database_path,
        clock=lambda: now[0],
    )

    return manager, now


def test_session_creation(environment):

    manager, _ = environment

    token = manager.create_session(1)

    assert valid_token_format(token)


def test_unique_session_tokens(environment):

    manager, _ = environment

    first = manager.create_session(1)
    second = manager.create_session(1)

    assert first != second


def test_token_stored_as_hash(
    environment,
    database_path,
):

    manager, _ = environment

    token = manager.create_session(1)

    with connect(database_path) as connection:

        row = connection.execute(
            "SELECT token_hash FROM auth_sessions"
        ).fetchone()

        assert row["token_hash"] != token
        assert row["token_hash"] == hash_token(token)
        assert len(row["token_hash"]) == 64


def test_valid_session(environment):

    manager, _ = environment

    token = manager.create_session(1)

    assert manager.validate_session(token) == 1


def test_unknown_session(environment):

    manager, _ = environment

    with pytest.raises(SessionDenied):

        manager.validate_session("a" * 43)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "short",
        "a" * 42,
        "a" * 44,
        "!" * 43,
        None,
        12345,
    ],
)
def test_invalid_token_format(environment, token):

    manager, _ = environment

    with pytest.raises(SessionDenied):

        manager.validate_session(token)


def test_session_persistence(
    environment,
    database_path,
):

    manager, now = environment

    token = manager.create_session(1)

    restarted = SessionManager(
        database_path,
        clock=lambda: now[0],
    )

    assert restarted.validate_session(token) == 1


def test_session_absolute_expiration(environment):

    manager, now = environment

    token = manager.create_session(1)

    elapsed = 0

    while elapsed < SESSION_DURATION - 1:

        interval = min(
            IDLE_TIMEOUT - 1,
            SESSION_DURATION - 1 - elapsed,
        )

        now[0] += interval
        elapsed += interval

        assert manager.validate_session(token) == 1

    now[0] += 1

    with pytest.raises(SessionDenied):

        manager.validate_session(token)


def test_idle_timeout(environment):

    manager, now = environment

    token = manager.create_session(1)

    now[0] += IDLE_TIMEOUT

    with pytest.raises(SessionDenied):

        manager.validate_session(token)


def test_activity_extends_idle_window(environment):

    manager, now = environment

    token = manager.create_session(1)

    now[0] += IDLE_TIMEOUT - 10

    assert manager.validate_session(token) == 1

    now[0] += IDLE_TIMEOUT - 10

    assert manager.validate_session(token) == 1


def test_last_seen_updated(
    environment,
    database_path,
):

    manager, now = environment

    token = manager.create_session(1)

    now[0] += 60

    manager.validate_session(token)

    with connect(database_path) as connection:

        row = connection.execute("""
            SELECT last_seen_at
            FROM auth_sessions
            WHERE token_hash = ?
        """, (hash_token(token),)).fetchone()

        assert row["last_seen_at"] == now[0]


def test_session_revocation(environment):

    manager, _ = environment

    token = manager.create_session(1)

    manager.revoke_session(token)

    with pytest.raises(SessionDenied):

        manager.validate_session(token)


def test_repeated_revocation(environment):

    manager, _ = environment

    token = manager.create_session(1)

    manager.revoke_session(token)
    manager.revoke_session(token)

    with pytest.raises(SessionDenied):

        manager.validate_session(token)


def test_revoke_all_sessions(environment):

    manager, _ = environment

    tokens = [
        manager.create_session(1)
        for _ in range(3)
    ]

    manager.revoke_all_sessions(1)

    for token in tokens:

        with pytest.raises(SessionDenied):

            manager.validate_session(token)


def test_inactive_owner_session_rejected(
    environment,
    database_path,
):

    manager, _ = environment

    token = manager.create_session(1)

    with connect(database_path) as connection:

        connection.execute(
            "UPDATE users SET is_active = 0 WHERE id = 1"
        )

    with pytest.raises(SessionDenied):

        manager.validate_session(token)


def test_inactive_owner_cannot_create_session(
    environment,
    database_path,
):

    manager, _ = environment

    with connect(database_path) as connection:

        connection.execute(
            "UPDATE users SET is_active = 0 WHERE id = 1"
        )

    with pytest.raises(SessionDenied):

        manager.create_session(1)


def test_unknown_owner_cannot_create_session(
    environment,
):

    manager, _ = environment

    with pytest.raises(SessionDenied):

        manager.create_session(99)


def test_clock_rollback_rejected(environment):

    manager, now = environment

    token = manager.create_session(1)

    now[0] -= 60

    with pytest.raises(SessionDenied):

        manager.validate_session(token)


def test_insecure_database_blocks_session(
    environment,
    database_path,
):

    manager, _ = environment

    token = manager.create_session(1)

    database_path.chmod(0o644)

    with pytest.raises(PermissionError):

        manager.validate_session(token)
