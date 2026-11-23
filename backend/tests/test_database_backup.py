import pytest

from aegis.storage.backup import create_backup
from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database
from aegis.storage.settings import load_settings


@pytest.fixture
def source_database(tmp_path):

    source = tmp_path / "private" / "source.sqlite3"

    initialize_database(source)

    return source


def test_backup_preserves_data(source_database):

    destination = (
        source_database.parent
        / "backups"
        / "backup.sqlite3"
    )

    create_backup(source_database, destination)

    assert (
        load_settings(destination)
        == load_settings(source_database)
    )

    with connect(destination) as connection:

        assert connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"


def test_backup_permissions(source_database):

    destination = (
        source_database.parent
        / "backups"
        / "backup.sqlite3"
    )

    create_backup(source_database, destination)

    assert destination.stat().st_mode & 0o777 == 0o600
    assert destination.parent.stat().st_mode & 0o777 == 0o700


def test_backup_never_overwrites(source_database):

    destination = (
        source_database.parent
        / "backup.sqlite3"
    )

    create_backup(source_database, destination)

    with pytest.raises(FileExistsError):
        create_backup(source_database, destination)


def test_backup_missing_source(tmp_path):

    with pytest.raises(FileNotFoundError):

        create_backup(
            tmp_path / "missing.sqlite3",
            tmp_path / "backup.sqlite3",
        )


def test_backup_rejects_insecure_directory(
    source_database,
):

    directory = source_database.parent / "insecure"

    directory.mkdir(mode=0o700)
    directory.chmod(0o755)

    with pytest.raises(PermissionError):

        create_backup(
            source_database,
            directory / "backup.sqlite3",
        )


def test_backup_rejects_destination_symlink(
    source_database,
):

    destination = (
        source_database.parent
        / "symlink.sqlite3"
    )

    destination.symlink_to(source_database)

    with pytest.raises(FileExistsError):
        create_backup(source_database, destination)


def test_backup_rejects_same_path(source_database):

    with pytest.raises(FileExistsError):
        create_backup(source_database, source_database)


def test_backup_rejects_source_symlink(source_database):

    link = source_database.parent / "source-link.sqlite3"
    link.symlink_to(source_database)

    with pytest.raises(FileNotFoundError):

        create_backup(
            link,
            source_database.parent / "backup.sqlite3",
        )
