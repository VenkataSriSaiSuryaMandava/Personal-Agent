from pathlib import Path

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


SCHEMA_VERSION = 1


def initialize_database(
    path: Path = DATABASE_PATH,
) -> None:

    with connect(path) as connection:

        connection.execute("BEGIN IMMEDIATE")

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if version > SCHEMA_VERSION:
            raise RuntimeError(
                "Unsupported database schema version"
            )

        if version == 0:

            connection.execute("""
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_api_usage_created_at
                ON api_usage(created_at)
            """)

            connection.execute("""
                INSERT INTO app_metadata (key, value)
                VALUES ('application', 'Aegis AI')
                ON CONFLICT(key) DO NOTHING
            """)

            connection.execute(
                "PRAGMA user_version = 1"
            )
