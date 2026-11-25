import os
import sqlite3
import stat

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aegis.storage.public_quota import apply_public_quota
from aegis.storage.access_policy import require_storage_access


PRIVATE_DIRECTORY = (
    Path.home()
    / "Library"
    / "Application Support"
    / "AegisAI"
)

DATABASE_PATH = PRIVATE_DIRECTORY / "aegis.sqlite3"


def prepare_database(path: Path) -> None:
    require_storage_access(path)


    path.parent.mkdir(
        mode=0o700,
        parents=True,
        exist_ok=True,
    )

    metadata = path.parent.lstat()

    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
    ):
        raise PermissionError(
            "Database directory is not private"
        )

    try:
        fd = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY
            | os.O_NOFOLLOW,
            0o600,
        )

        os.close(fd)

    except FileExistsError:
        pass

    metadata = path.lstat()

    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
    ):
        raise PermissionError(
            "Database file is not private"
        )


@contextmanager
def connect(
    path: Path = DATABASE_PATH,
) -> Iterator[sqlite3.Connection]:

    prepare_database(path)

    connection = sqlite3.connect(
        path,
        timeout=5,
    )

    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        apply_public_quota(connection, path)


        yield connection

        connection.commit()

    except BaseException:
        connection.rollback()
        raise

    finally:
        connection.close()
