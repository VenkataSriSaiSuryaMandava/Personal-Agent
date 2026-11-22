from concurrent.futures import ThreadPoolExecutor

import pytest

from aegis.security.login_limit import (
    LoginRateLimiter,
    LoginLimitExceeded,
    LoginStorageUnavailable,
    MAX_LOGIN_ATTEMPTS,
    LOGIN_WINDOW,
)

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


@pytest.fixture
def database_path(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "login.sqlite3"

    initialize_database(path)

    return path


@pytest.fixture
def environment(database_path):

    now = [100000]

    limiter = LoginRateLimiter(
        database_path,
        clock=lambda: now[0],
    )

    return limiter, now


def test_first_attempt_allowed(environment):

    limiter, _ = environment

    assert limiter.acquire() > 0


def test_maximum_attempts_allowed(environment):

    limiter, _ = environment

    for _ in range(MAX_LOGIN_ATTEMPTS):
        limiter.acquire()


def test_excess_attempt_blocked(environment):

    limiter, _ = environment

    for _ in range(MAX_LOGIN_ATTEMPTS):
        limiter.acquire()

    with pytest.raises(LoginLimitExceeded):
        limiter.acquire()


def test_restart_persistence(
    environment,
    database_path,
):

    limiter, now = environment

    for _ in range(MAX_LOGIN_ATTEMPTS):
        limiter.acquire()

    restarted = LoginRateLimiter(
        database_path,
        clock=lambda: now[0],
    )

    with pytest.raises(LoginLimitExceeded):
        restarted.acquire()


def test_window_expiration(environment):

    limiter, now = environment

    for _ in range(MAX_LOGIN_ATTEMPTS):
        limiter.acquire()

    now[0] += LOGIN_WINDOW

    assert limiter.acquire() > 0


def test_window_not_expired(environment):

    limiter, now = environment

    for _ in range(MAX_LOGIN_ATTEMPTS):
        limiter.acquire()

    now[0] += LOGIN_WINDOW - 1

    with pytest.raises(LoginLimitExceeded):
        limiter.acquire()


def test_successful_login_resets_limit(environment):

    limiter, _ = environment

    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        limiter.acquire()

    successful_attempt = limiter.acquire()

    limiter.record_success(successful_attempt)

    for _ in range(MAX_LOGIN_ATTEMPTS):
        limiter.acquire()

    with pytest.raises(LoginLimitExceeded):
        limiter.acquire()


def test_success_preserves_newer_attempts(
    environment,
    database_path,
):

    limiter, _ = environment

    limiter.acquire()
    successful_attempt = limiter.acquire()
    newer_attempt = limiter.acquire()

    limiter.record_success(successful_attempt)

    with connect(database_path) as connection:

        rows = connection.execute("""
            SELECT id FROM login_attempts
        """).fetchall()

        assert len(rows) == 1
        assert rows[0]["id"] == newer_attempt


def test_unknown_attempt_rejected(environment):

    limiter, _ = environment

    with pytest.raises(LoginStorageUnavailable):
        limiter.record_success(99999)


def test_repeated_success_rejected(environment):

    limiter, _ = environment

    attempt = limiter.acquire()

    limiter.record_success(attempt)

    with pytest.raises(LoginStorageUnavailable):
        limiter.record_success(attempt)


def test_concurrent_login_attempts(database_path):

    def attempt(_):

        limiter = LoginRateLimiter(
            database_path,
            clock=lambda: 100000,
        )

        try:

            limiter.acquire()
            return True

        except LoginLimitExceeded:

            return False

    with ThreadPoolExecutor(max_workers=10) as executor:

        results = list(
            executor.map(attempt, range(10))
        )

    assert sum(results) == MAX_LOGIN_ATTEMPTS


def test_attempt_contains_no_credentials(
    environment,
    database_path,
):

    limiter, _ = environment

    limiter.acquire()

    with connect(database_path) as connection:

        row = connection.execute("""
            SELECT * FROM login_attempts
        """).fetchone()

        assert set(row.keys()) == {
            "id",
            "attempted_at",
            "successful",
        }

        assert row["successful"] == 0


def test_expired_attempt_cleanup(
    environment,
    database_path,
):

    limiter, now = environment

    for _ in range(MAX_LOGIN_ATTEMPTS):
        limiter.acquire()

    now[0] += LOGIN_WINDOW

    limiter.acquire()

    with connect(database_path) as connection:

        count = connection.execute("""
            SELECT COUNT(*) FROM login_attempts
        """).fetchone()[0]

        assert count == 1


def test_insecure_database_blocks_login(
    environment,
    database_path,
):

    limiter, _ = environment

    database_path.chmod(0o644)

    with pytest.raises(LoginStorageUnavailable):
        limiter.acquire()


def test_uninitialized_database_blocks_login(tmp_path):

    directory = tmp_path / "uninitialized"
    directory.mkdir(mode=0o700)

    limiter = LoginRateLimiter(
        directory / "missing.sqlite3"
    )

    with pytest.raises(LoginStorageUnavailable):
        limiter.acquire()
