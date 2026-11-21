from concurrent.futures import ThreadPoolExecutor

import pytest

from aegis.security.rate_limit import (
    PersistentRateLimiter,
    RateLimitExceeded,
    UsageStorageUnavailable,
)

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


@pytest.fixture
def database_path(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "usage.sqlite3"

    initialize_database(path)

    return path


def test_minute_limit(database_path):

    limiter = PersistentRateLimiter(database_path)

    for _ in range(3):
        limiter.acquire()

    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_restart_persistence(database_path):

    first = PersistentRateLimiter(database_path)

    for _ in range(3):
        first.acquire()

    second = PersistentRateLimiter(database_path)

    with pytest.raises(RateLimitExceeded):
        second.acquire()


def test_minute_window_expiration(database_path):

    now = [100000]

    limiter = PersistentRateLimiter(
        database_path,
        clock=lambda: now[0],
    )

    for _ in range(3):
        limiter.acquire()

    now[0] += 60

    limiter.acquire()


def test_daily_limit(database_path):

    now = [100000]

    limiter = PersistentRateLimiter(
        database_path,
        clock=lambda: now[0],
    )

    for _ in range(10):

        for _ in range(3):
            limiter.acquire()

        now[0] += 60

    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_daily_window_expiration(database_path):

    now = [100000]

    limiter = PersistentRateLimiter(
        database_path,
        clock=lambda: now[0],
    )

    for _ in range(3):
        limiter.acquire()

    now[0] += 86400

    limiter.acquire()

    with connect(database_path) as connection:

        count = connection.execute(
            "SELECT COUNT(*) FROM api_usage"
        ).fetchone()[0]

        assert count == 1


def test_concurrent_requests(database_path):

    def attempt(_):

        limiter = PersistentRateLimiter(database_path)

        try:
            limiter.acquire()
            return True

        except RateLimitExceeded:
            return False

    with ThreadPoolExecutor(max_workers=10) as executor:

        results = list(executor.map(attempt, range(10)))

    assert sum(results) == 3


def test_uninitialized_database(tmp_path):

    directory = tmp_path / "uninitialized"
    directory.mkdir(mode=0o700)

    limiter = PersistentRateLimiter(
        directory / "usage.sqlite3"
    )

    with pytest.raises(UsageStorageUnavailable):
        limiter.acquire()


def test_insecure_database_permissions(database_path):

    database_path.chmod(0o644)

    limiter = PersistentRateLimiter(database_path)

    with pytest.raises(UsageStorageUnavailable):
        limiter.acquire()


def test_usage_record_contents(database_path):

    limiter = PersistentRateLimiter(
        database_path,
        clock=lambda: 100000,
    )

    limiter.acquire()

    with connect(database_path) as connection:

        row = connection.execute("""
            SELECT provider, created_at
            FROM api_usage
        """).fetchone()

        assert row["provider"] == "gemini"
        assert row["created_at"] == 100000
