import sqlite3

import pytest

from aegis.security.owner import (
    create_owner,
    reset_owner_password,
    OwnerNotConfigured,
)

from aegis.security.authentication import (
    AuthenticationService,
    AuthenticationDenied,
)

from aegis.security.passwords import InvalidPassword

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


USERNAME = "test-owner"
ORIGINAL = "Synthetic original password 2026!"
REPLACEMENT = "Synthetic replacement password 2026!"


@pytest.fixture
def database_path(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "recovery.sqlite3"

    initialize_database(path)

    return path


@pytest.fixture
def environment(database_path):

    create_owner(
        USERNAME,
        ORIGINAL,
        database_path,
    )

    service = AuthenticationService(database_path)

    return service, database_path


def test_password_replacement(environment):

    service, path = environment

    reset_owner_password(REPLACEMENT, path)

    token = service.login(USERNAME, REPLACEMENT)

    assert service.authenticate(token) == 1


def test_old_password_rejected(environment):

    service, path = environment

    reset_owner_password(REPLACEMENT, path)

    with pytest.raises(AuthenticationDenied):

        service.login(USERNAME, ORIGINAL)


def test_all_sessions_revoked(environment):

    service, path = environment

    tokens = [
        service.login(USERNAME, ORIGINAL)
        for _ in range(3)
    ]

    reset_owner_password(REPLACEMENT, path)

    for token in tokens:

        with pytest.raises(AuthenticationDenied):

            service.authenticate(token)


def test_login_attempts_reset(environment):

    service, path = environment

    for _ in range(5):

        with pytest.raises(AuthenticationDenied):

            service.login(
                USERNAME,
                "Incorrect password",
            )

    reset_owner_password(REPLACEMENT, path)

    with connect(path) as connection:

        count = connection.execute(
            "SELECT COUNT(*) FROM login_attempts"
        ).fetchone()[0]

        assert count == 0

    assert service.login(USERNAME, REPLACEMENT)


def test_invalid_replacement_preserves_password(
    environment,
):

    service, path = environment

    with pytest.raises(InvalidPassword):

        reset_owner_password("short", path)

    assert service.login(USERNAME, ORIGINAL)


def test_recovery_without_owner(database_path):

    with pytest.raises(OwnerNotConfigured):

        reset_owner_password(
            REPLACEMENT,
            database_path,
        )


def test_inactive_owner_recovery_denied(environment):

    _, path = environment

    with connect(path) as connection:

        connection.execute(
            "UPDATE users SET is_active = 0"
        )

    with pytest.raises(OwnerNotConfigured):

        reset_owner_password(REPLACEMENT, path)


def test_recovery_rollback(environment):

    service, path = environment

    token = service.login(USERNAME, ORIGINAL)

    with connect(path) as connection:

        connection.execute("""
            CREATE TRIGGER reject_session_revocation
            BEFORE UPDATE ON auth_sessions
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Synthetic recovery failure'
                );
            END
        """)

    with pytest.raises(sqlite3.Error):

        reset_owner_password(REPLACEMENT, path)

    with connect(path) as connection:

        connection.execute("""
            DROP TRIGGER reject_session_revocation
        """)

    assert service.authenticate(token) == 1
    assert service.login(USERNAME, ORIGINAL)

    with pytest.raises(AuthenticationDenied):

        service.login(USERNAME, REPLACEMENT)


def test_insecure_database_blocks_recovery(
    environment,
):

    _, path = environment

    path.chmod(0o644)

    with pytest.raises(PermissionError):

        reset_owner_password(REPLACEMENT, path)
