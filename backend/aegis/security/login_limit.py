import sqlite3
import time

from pathlib import Path
from typing import Callable

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW = 15 * 60


class LoginLimitExceeded(Exception):
    """Login attempt limit has been reached."""


class LoginStorageUnavailable(Exception):
    """Secure login storage is unavailable."""


class LoginRateLimiter:

    def __init__(
        self,
        path: Path = DATABASE_PATH,
        clock: Callable[[], float] = time.time,
    ):

        self.path = path
        self.clock = clock

    def acquire(self) -> int:

        try:

            with connect(self.path) as connection:

                connection.execute("BEGIN IMMEDIATE")

                now = int(self.clock())
                cutoff = now - LOGIN_WINDOW

                connection.execute("""
                    DELETE FROM login_attempts
                    WHERE attempted_at <= ?
                """, (cutoff,))

                count = connection.execute("""
                    SELECT COUNT(*)
                    FROM login_attempts
                """).fetchone()[0]

                if count >= MAX_LOGIN_ATTEMPTS:

                    raise LoginLimitExceeded(
                        "Login attempt limit reached"
                    )

                cursor = connection.execute("""
                    INSERT INTO login_attempts (
                        attempted_at,
                        successful
                    )
                    VALUES (?, 0)
                """, (now,))

                return cursor.lastrowid

        except LoginLimitExceeded:
            raise

        except (sqlite3.Error, OSError):

            raise LoginStorageUnavailable(
                "Secure login storage unavailable"
            ) from None

    def record_success(
        self,
        attempt_id: int,
    ) -> None:

        try:

            with connect(self.path) as connection:

                connection.execute("BEGIN IMMEDIATE")

                cursor = connection.execute("""
                    UPDATE login_attempts
                    SET successful = 1
                    WHERE id = ?
                    AND successful = 0
                """, (attempt_id,))

                if cursor.rowcount != 1:

                    raise LoginStorageUnavailable(
                        "Invalid login attempt"
                    )

                connection.execute("""
                    DELETE FROM login_attempts
                    WHERE id <= ?
                """, (attempt_id,))

        except (sqlite3.Error, OSError):

            raise LoginStorageUnavailable(
                "Secure login storage unavailable"
            ) from None
