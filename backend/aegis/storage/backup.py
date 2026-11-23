import os
import sqlite3
from contextlib import closing
from pathlib import Path

from aegis.storage.database import (
    connect,
    prepare_database,
)


def create_backup(
    source: Path,
    destination: Path,
) -> Path:
    """Create a consistent, private SQLite backup."""

    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(
            "Source database is unavailable"
        )

    prepare_database(source)

    destination.parent.mkdir(
        mode=0o700,
        parents=True,
        exist_ok=True,
    )

    parent = destination.parent.lstat()

    if (
        destination.parent.is_symlink()
        or not destination.parent.is_dir()
        or parent.st_uid != os.getuid()
        or parent.st_mode & 0o077
    ):
        raise PermissionError(
            "Backup directory is not private"
        )

    fd = os.open(
        destination,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW,
        0o600,
    )

    os.close(fd)

    try:
        with closing(sqlite3.connect(
            source.absolute().as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
        )) as original:

            with connect(destination) as backup:

                original.backup(backup)

                result = [
                    row[0]
                    for row in backup.execute(
                        "PRAGMA integrity_check"
                    )
                ]

                if result != ["ok"]:
                    raise RuntimeError(
                        "Backup integrity verification failed"
                    )

        return destination

    except BaseException:
        destination.unlink(missing_ok=True)
        raise
