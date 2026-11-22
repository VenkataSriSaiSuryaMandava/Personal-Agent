from concurrent.futures import ThreadPoolExecutor

import pytest

from aegis.security.owner import (
    create_owner,
    owner_exists,
    normalize_username,
    OwnerAlreadyExists,
    InvalidUsername,
)

from aegis.security.passwords import (
    InvalidPassword,
    verify_password,
)

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


SYNTHETIC_PASSWORD = "Synthetic owner password 2026!"


@pytest.fixture
def database_path(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "owner.sqlite3"

    initialize_database(path)

    return path


def test_no_owner_initially(database_path):

    assert not owner_exists(database_path)


def test_create_owner(database_path):

    create_owner(
        "test-owner",
        SYNTHETIC_PASSWORD,
        database_path,
    )

    assert owner_exists(database_path)


def test_username_normalization():

    assert normalize_username(
        "  Test-Owner  "
    ) == "test-owner"


@pytest.mark.parametrize(
    "username",
    [
        "",
        "ab",
        "a" * 33,
        "invalid username",
        "../owner",
        "owner@example.com",
        "<owner>",
        None,
        12345,
    ],
)
def test_invalid_username(username):

    with pytest.raises(InvalidUsername):

        normalize_username(username)


def test_password_hash_storage(database_path):

    create_owner(
        "test-owner",
        SYNTHETIC_PASSWORD,
        database_path,
    )

    with connect(database_path) as connection:

        owner = connection.execute(
            "SELECT * FROM users WHERE id = 1"
        ).fetchone()

        assert owner["password_hash"].startswith(
            "$argon2id$"
        )

        assert SYNTHETIC_PASSWORD not in (
            owner["password_hash"]
        )

        assert verify_password(
            SYNTHETIC_PASSWORD,
            owner["password_hash"],
        )


def test_owner_active_by_default(database_path):

    create_owner(
        "test-owner",
        SYNTHETIC_PASSWORD,
        database_path,
    )

    with connect(database_path) as connection:

        owner = connection.execute(
            "SELECT is_active FROM users WHERE id = 1"
        ).fetchone()

        assert owner["is_active"] == 1


def test_duplicate_owner_rejected(database_path):

    create_owner(
        "test-owner",
        SYNTHETIC_PASSWORD,
        database_path,
    )

    with pytest.raises(OwnerAlreadyExists):

        create_owner(
            "second-owner",
            SYNTHETIC_PASSWORD,
            database_path,
        )


def test_invalid_password_creates_no_owner(
    database_path,
):

    with pytest.raises(InvalidPassword):

        create_owner(
            "test-owner",
            "short",
            database_path,
        )

    assert not owner_exists(database_path)


def test_invalid_username_creates_no_owner(
    database_path,
):

    with pytest.raises(InvalidUsername):

        create_owner(
            "invalid username",
            SYNTHETIC_PASSWORD,
            database_path,
        )

    assert not owner_exists(database_path)


def test_duplicate_does_not_overwrite_owner(
    database_path,
):

    create_owner(
        "original-owner",
        SYNTHETIC_PASSWORD,
        database_path,
    )

    with pytest.raises(OwnerAlreadyExists):

        create_owner(
            "replacement-owner",
            "Different synthetic password 2026!",
            database_path,
        )

    with connect(database_path) as connection:

        owner = connection.execute(
            "SELECT * FROM users WHERE id = 1"
        ).fetchone()

        assert owner["username"] == "original-owner"

        assert verify_password(
            SYNTHETIC_PASSWORD,
            owner["password_hash"],
        )


def test_concurrent_owner_creation(database_path):

    def attempt(index):

        try:

            create_owner(
                f"owner-{index}",
                SYNTHETIC_PASSWORD,
                database_path,
            )

            return True

        except OwnerAlreadyExists:

            return False

    with ThreadPoolExecutor(max_workers=4) as executor:

        results = list(
            executor.map(attempt, range(4))
        )

    assert sum(results) == 1

    with connect(database_path) as connection:

        count = connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        assert count == 1
