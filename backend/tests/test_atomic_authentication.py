from concurrent.futures import ThreadPoolExecutor

import pytest

from aegis.security.authentication import (
    AuthenticationService,
    AuthenticationDenied,
    AuthenticationUnavailable,
)

from aegis.security.login_limit import (
    LoginLimitExceeded,
    MAX_LOGIN_ATTEMPTS,
    LOGIN_WINDOW,
)

from aegis.security.owner import create_owner
from aegis.security.passwords import hash_password
from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


USERNAME = "test-owner"
PASSWORD = "Synthetic owner password 2026!"


@pytest.fixture
def environment(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "auth.sqlite3"

    initialize_database(path)

    create_owner(USERNAME, PASSWORD, path)

    now = [100000]

    service = AuthenticationService(
        path,
        clock=lambda: now[0],
    )

    return service, path, now


def test_successful_atomic_login(environment):

    service, path, _ = environment

    token = service.login(USERNAME, PASSWORD)

    assert service.authenticate(token) == 1

    with connect(path) as connection:

        sessions = connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0]

        attempts = connection.execute(
            "SELECT COUNT(*) FROM login_attempts"
        ).fetchone()[0]

    assert sessions == 1
    assert attempts == 0


def test_session_insert_failure_preserves_attempt(
    environment,
):

    service, path, _ = environment

    with connect(path) as connection:

        connection.execute("""
            CREATE TRIGGER reject_session_insert
            BEFORE INSERT ON auth_sessions
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Synthetic session failure'
                );
            END
        """)

    with pytest.raises(AuthenticationUnavailable):

        service.login(USERNAME, PASSWORD)

    with connect(path) as connection:

        sessions = connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0]

        attempts = connection.execute(
            "SELECT COUNT(*) FROM login_attempts"
        ).fetchone()[0]

    assert sessions == 0
    assert attempts == 1


def test_attempt_cleanup_failure_rolls_back_session(
    environment,
):

    service, path, _ = environment

    with connect(path) as connection:

        connection.execute("""
            CREATE TRIGGER reject_attempt_cleanup
            BEFORE DELETE ON login_attempts
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Synthetic cleanup failure'
                );
            END
        """)

    with pytest.raises(AuthenticationUnavailable):

        service.login(USERNAME, PASSWORD)

    with connect(path) as connection:

        sessions = connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0]

        attempts = connection.execute(
            "SELECT COUNT(*) FROM login_attempts"
        ).fetchone()[0]

    assert sessions == 0
    assert attempts == 1


def test_password_changed_during_login(
    environment,
    monkeypatch,
):

    service, path, _ = environment

    original = service._finalize_login

    def change_password(*args):

        replacement = hash_password(
            "Replacement synthetic password 2026!"
        )

        with connect(path) as connection:

            connection.execute("""
                UPDATE users
                SET password_hash = ?
                WHERE id = 1
            """, (replacement,))

        return original(*args)

    monkeypatch.setattr(
        service,
        "_finalize_login",
        change_password,
    )

    with pytest.raises(AuthenticationDenied):

        service.login(USERNAME, PASSWORD)

    with connect(path) as connection:

        assert connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0] == 0


def test_owner_disabled_during_login(
    environment,
    monkeypatch,
):

    service, path, _ = environment

    original = service._finalize_login

    def disable_owner(*args):

        with connect(path) as connection:

            connection.execute("""
                UPDATE users
                SET is_active = 0
                WHERE id = 1
            """)

        return original(*args)

    monkeypatch.setattr(
        service,
        "_finalize_login",
        disable_owner,
    )

    with pytest.raises(AuthenticationDenied):

        service.login(USERNAME, PASSWORD)


def test_login_attempt_expires_during_verification(
    environment,
    monkeypatch,
):

    service, _, now = environment

    original = service._finalize_login

    def expire_attempt(*args):

        now[0] += LOGIN_WINDOW

        return original(*args)

    monkeypatch.setattr(
        service,
        "_finalize_login",
        expire_attempt,
    )

    with pytest.raises(AuthenticationDenied):

        service.login(USERNAME, PASSWORD)


def test_concurrent_failed_logins(environment):

    service, path, _ = environment

    def attempt(_):

        try:

            service.login(
                USERNAME,
                "Incorrect synthetic password",
            )

        except AuthenticationDenied:

            return "denied"

        except LoginLimitExceeded:

            return "limited"

        return "unexpected"

    with ThreadPoolExecutor(max_workers=10) as executor:

        results = list(
            executor.map(attempt, range(10))
        )

    assert results.count("denied") == MAX_LOGIN_ATTEMPTS
    assert results.count("limited") == 5
    assert "unexpected" not in results

    with connect(path) as connection:

        assert connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0] == 0


def test_concurrent_successful_logins(environment):

    service, path, _ = environment

    def attempt(_):

        try:

            return service.login(USERNAME, PASSWORD)

        except (
            AuthenticationDenied,
            LoginLimitExceeded,
        ):

            return None

    with ThreadPoolExecutor(max_workers=4) as executor:

        results = list(
            executor.map(attempt, range(4))
        )

    tokens = [
        token for token in results
        if token is not None
    ]

    assert len(tokens) >= 1
    assert len(tokens) == len(set(tokens))

    for token in tokens:

        assert service.authenticate(token) == 1

    with connect(path) as connection:

        count = connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0]

    assert count == len(tokens)
