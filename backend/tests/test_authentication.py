import pytest

from aegis.security.authentication import (
    AuthenticationService,
    AuthenticationDenied,
    AuthenticationUnavailable,
)

from aegis.security.login_limit import (
    LoginLimitExceeded,
    MAX_LOGIN_ATTEMPTS,
    LOGIN_WINDOW,
)

from aegis.security.sessions import IDLE_TIMEOUT

from aegis.security.owner import create_owner
from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


USERNAME = "test-owner"
PASSWORD = "Synthetic owner password 2026!"


@pytest.fixture
def database_path(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "auth.sqlite3"

    initialize_database(path)

    create_owner(USERNAME, PASSWORD, path)

    return path


@pytest.fixture
def environment(database_path):

    now = [100000]

    service = AuthenticationService(
        database_path,
        clock=lambda: now[0],
    )

    return service, now


def test_successful_login(environment):

    service, _ = environment

    token = service.login(USERNAME, PASSWORD)

    assert service.authenticate(token) == 1


def test_normalized_username_login(environment):

    service, _ = environment

    token = service.login(
        "  TEST-OWNER  ",
        PASSWORD,
    )

    assert service.authenticate(token) == 1


def test_incorrect_password(environment):

    service, _ = environment

    with pytest.raises(
        AuthenticationDenied,
        match="Invalid credentials",
    ):

        service.login(
            USERNAME,
            "Incorrect password",
        )


def test_unknown_username(environment):

    service, _ = environment

    with pytest.raises(
        AuthenticationDenied,
        match="Invalid credentials",
    ):

        service.login(
            "unknown-owner",
            PASSWORD,
        )


@pytest.mark.parametrize(
    "username",
    ["", None, "invalid username"],
)
def test_invalid_username(environment, username):

    service, _ = environment

    with pytest.raises(AuthenticationDenied):

        service.login(username, PASSWORD)


@pytest.mark.parametrize(
    "password",
    ["", None, "a" * 129, 12345],
)
def test_invalid_password(environment, password):

    service, _ = environment

    with pytest.raises(AuthenticationDenied):

        service.login(USERNAME, password)


def test_failed_login_creates_no_session(
    environment,
    database_path,
):

    service, _ = environment

    with pytest.raises(AuthenticationDenied):

        service.login(USERNAME, "Incorrect password")

    with connect(database_path) as connection:

        count = connection.execute("""
            SELECT COUNT(*) FROM auth_sessions
        """).fetchone()[0]

    assert count == 0


def test_login_rate_limit(environment):

    service, _ = environment

    for _ in range(MAX_LOGIN_ATTEMPTS):

        with pytest.raises(AuthenticationDenied):

            service.login(
                USERNAME,
                "Incorrect password",
            )

    with pytest.raises(LoginLimitExceeded):

        service.login(USERNAME, PASSWORD)


def test_unknown_users_consume_quota(environment):

    service, _ = environment

    for index in range(MAX_LOGIN_ATTEMPTS):

        with pytest.raises(AuthenticationDenied):

            service.login(
                f"unknown-{index}",
                PASSWORD,
            )

    with pytest.raises(LoginLimitExceeded):

        service.login(USERNAME, PASSWORD)


def test_login_after_cooldown(environment):

    service, now = environment

    for _ in range(MAX_LOGIN_ATTEMPTS):

        with pytest.raises(AuthenticationDenied):

            service.login(
                USERNAME,
                "Incorrect password",
            )

    now[0] += LOGIN_WINDOW

    token = service.login(USERNAME, PASSWORD)

    assert service.authenticate(token) == 1


def test_successful_login_resets_quota(environment):

    service, _ = environment

    for _ in range(MAX_LOGIN_ATTEMPTS - 1):

        with pytest.raises(AuthenticationDenied):

            service.login(
                USERNAME,
                "Incorrect password",
            )

    service.login(USERNAME, PASSWORD)

    for _ in range(MAX_LOGIN_ATTEMPTS):

        with pytest.raises(AuthenticationDenied):

            service.login(
                USERNAME,
                "Incorrect password",
            )


def test_logout(environment):

    service, _ = environment

    token = service.login(USERNAME, PASSWORD)

    service.logout(token)

    with pytest.raises(AuthenticationDenied):

        service.authenticate(token)


def test_expired_session(environment):

    service, now = environment

    token = service.login(USERNAME, PASSWORD)

    now[0] += IDLE_TIMEOUT

    with pytest.raises(AuthenticationDenied):

        service.authenticate(token)


def test_invalid_session_token(environment):

    service, _ = environment

    with pytest.raises(AuthenticationDenied):

        service.authenticate("invalid-token")


def test_inactive_owner_cannot_login(
    environment,
    database_path,
):

    service, _ = environment

    with connect(database_path) as connection:

        connection.execute("""
            UPDATE users
            SET is_active = 0
            WHERE id = 1
        """)

    with pytest.raises(AuthenticationDenied):

        service.login(USERNAME, PASSWORD)


def test_restart_preserves_session(
    environment,
    database_path,
):

    service, now = environment

    token = service.login(USERNAME, PASSWORD)

    restarted = AuthenticationService(
        database_path,
        clock=lambda: now[0],
    )

    assert restarted.authenticate(token) == 1


def test_insecure_database_blocks_login(
    environment,
    database_path,
):

    service, _ = environment

    database_path.chmod(0o644)

    with pytest.raises(AuthenticationUnavailable):

        service.login(USERNAME, PASSWORD)


def test_insecure_database_blocks_session(
    environment,
    database_path,
):

    service, _ = environment

    token = service.login(USERNAME, PASSWORD)

    database_path.chmod(0o644)

    with pytest.raises(AuthenticationUnavailable):

        service.authenticate(token)


def test_insecure_database_blocks_logout(
    environment,
    database_path,
):

    service, _ = environment

    token = service.login(USERNAME, PASSWORD)

    database_path.chmod(0o644)

    with pytest.raises(AuthenticationUnavailable):

        service.logout(token)


def test_unconfigured_owner(tmp_path):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "auth.sqlite3"

    initialize_database(path)

    service = AuthenticationService(path)

    with pytest.raises(
        AuthenticationDenied,
        match="Invalid credentials",
    ):

        service.login(USERNAME, PASSWORD)
