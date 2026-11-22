import sqlite3
import time

from pathlib import Path
from typing import Callable

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


class RateLimitExceeded(Exception):
    pass


class UsageStorageUnavailable(Exception):
    pass


class PersistentRateLimiter:

    def __init__(
        self,
        path: Path = DATABASE_PATH,
        clock: Callable[[], float] = time.time,
    ):
        self.path = path
        self.clock = clock

    def acquire(self) -> None:

        # Optional application-level AI usage limits.
        import os

        if os.getenv("AEGIS_UNLIMITED_AI") == "1":
            return


        now = int(self.clock())

        minute_start = now - 60
        day_start = now - 86400

        try:
            with connect(self.path) as connection:

                connection.execute("BEGIN IMMEDIATE")

                connection.execute(
                    """
                    DELETE FROM api_usage
                    WHERE created_at <= ?
                    """,
                    (day_start,),
                )

                daily_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM api_usage
                    WHERE provider = ?
                    """,
                    ("gemini",),
                ).fetchone()[0]

                minute_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM api_usage
                    WHERE provider = ?
                    AND created_at > ?
                    """,
                    ("gemini", minute_start),
                ).fetchone()[0]

                if minute_count >= 3:
                    raise RateLimitExceeded(
                        "Per-minute limit reached"
                    )

                if daily_count >= 30:
                    raise RateLimitExceeded(
                        "Daily limit reached"
                    )

                connection.execute(
                    """
                    INSERT INTO api_usage (
                        provider,
                        created_at
                    )
                    VALUES (?, ?)
                    """,
                    ("gemini", now),
                )

        except RateLimitExceeded:
            raise

        except (sqlite3.Error, OSError) as error:
            raise UsageStorageUnavailable(
                "Usage storage unavailable"
            ) from None
