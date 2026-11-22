import pytest

from fastapi.testclient import TestClient

from aegis.api import auth
from aegis.main import app

from aegis.security.authentication import (
    AuthenticationService,
)

from aegis.security.owner import create_owner

from aegis.storage.migrations import (
    initialize_database,
)


TEST_USERNAME = "test-owner"
TEST_PASSWORD = "Synthetic protected API password!"
TEST_GATEWAY = "a" * 64


@pytest.fixture
def authenticated_environment(
    tmp_path,
    monkeypatch,
):

    directory = tmp_path / "authenticated"
    directory.mkdir(mode=0o700)

    path = directory / "auth.sqlite3"

    initialize_database(path)

    create_owner(
        TEST_USERNAME,
        TEST_PASSWORD,
        path,
    )

    now = [100000]

    service = AuthenticationService(
        path,
        clock=lambda: now[0],
    )

    monkeypatch.setattr(
        auth,
        "service",
        service,
    )

    monkeypatch.setenv(
        "AEGIS_GATEWAY_TOKEN",
        TEST_GATEWAY,
    )

    monkeypatch.setenv(
        "AEGIS_CLOUD_ENABLED",
        "0",
    )

    token = service.login(
        TEST_USERNAME,
        TEST_PASSWORD,
    )

    headers = {
        "x-aegis-gateway-token": TEST_GATEWAY,
        "Authorization": f"Bearer {token}",
    }

    with TestClient(app, headers=headers) as client:

        yield client, service, token, path, now
