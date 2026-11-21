import argparse

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)
from aegis.storage.migrations import initialize_database


def main():

    parser = argparse.ArgumentParser(
        description="Aegis local database management"
    )

    parser.add_argument(
        "command",
        choices=["init", "status"],
    )

    args = parser.parse_args()

    if args.command == "init":

        initialize_database()

        print("Local database initialized.")
        return 0

    if not DATABASE_PATH.exists():

        print("Local database is not initialized.")
        return 1

    with connect() as connection:

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        print(f"Schema version: {version}")
        print(f"Integrity: {integrity}")

    return 0 if integrity == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
