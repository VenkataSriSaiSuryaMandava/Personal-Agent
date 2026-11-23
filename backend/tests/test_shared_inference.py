import sys

from unittest.mock import patch

import pytest


from aegis.cli.inference import main as cli_main
from aegis.security.access import limiter
from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database


TEST_TOKEN = "a" * 64

VALID_REQUEST = {
    "prompt_id": "general_knowledge",
    "approved": True,
}


@pytest.fixture
def environment(
    monkeypatch,
    tmp_path,
    authenticated_environment,
):

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "usage.sqlite3"

    initialize_database(path)

    # The owner authentication fixture already provides
    # an isolated database containing application settings.
    # Keep its security permissions separate from the
    # usage database so quota-failure tests remain valid.
    from aegis.security.runtime_controls import runtime_controls
    from aegis.storage.settings import (
        ApplicationSettings,
        save_settings,
    )

    security_path = authenticated_environment[3]

    save_settings(
        ApplicationSettings(cloud_enabled=True),
        1,
        security_path,
    )

    monkeypatch.setattr(
        runtime_controls,
        "path",
        security_path,
    )

    monkeypatch.setattr(limiter, "path", path)

    monkeypatch.setattr(
        limiter, "clock", lambda: 100000
    )

    monkeypatch.setenv("AEGIS_GATEWAY_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")
    monkeypatch.setenv("AEGIS_EMERGENCY_STOP", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    client = authenticated_environment[0]

    return client, path


def usage_count(path):

    with connect(path) as connection:

        return connection.execute(
            "SELECT COUNT(*) FROM api_usage"
        ).fetchone()[0]


def invoke_cli(monkeypatch, approve=True):

    arguments = [
        "inference",
        "--prompt",
        "general_knowledge",
    ]

    if approve:
        arguments.append("--approve")

    monkeypatch.setattr(sys, "argv", arguments)

    return cli_main()


def test_api_and_cli_share_quota(
    environment,
    monkeypatch,
    capsys,
):

    client, path = environment

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        provider.return_value.complete.return_value = (
            "Synthetic AI response"
        )

        for _ in range(2):

            response = client.post(
                "/api/v1/inference",
                json=VALID_REQUEST,
            )

            assert response.status_code == 200

        assert invoke_cli(monkeypatch) == 0

        assert usage_count(path) == 3

        response = client.post(
            "/api/v1/inference",
            json=VALID_REQUEST,
        )

        assert response.status_code == 429

        assert invoke_cli(monkeypatch) == 1

        assert "limit reached" in capsys.readouterr().out

        assert provider.return_value.complete.call_count == 3

        assert usage_count(path) == 3


@pytest.mark.parametrize(
    "variable,value",
    [
        ("AEGIS_CLOUD_ENABLED", "0"),
        ("AEGIS_EMERGENCY_STOP", "1"),
        ("GEMINI_MODEL", "unauthorized-model"),
    ],
)
def test_policy_rejections_do_not_consume_quota(
    environment,
    monkeypatch,
    variable,
    value,
):

    client, path = environment

    monkeypatch.setenv(variable, value)

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        response = client.post(
            "/api/v1/inference",
            json=VALID_REQUEST,
        )

        assert response.status_code == 403

        provider.assert_not_called()

        assert usage_count(path) == 0


def test_missing_key_does_not_consume_quota(
    environment,
    monkeypatch,
):

    client, path = environment

    monkeypatch.delenv("GEMINI_API_KEY")

    response = client.post(
        "/api/v1/inference",
        json=VALID_REQUEST,
    )

    assert response.status_code == 503

    assert usage_count(path) == 0


def test_missing_cli_approval_does_not_consume_quota(
    environment,
    monkeypatch,
):

    _, path = environment

    assert invoke_cli(
        monkeypatch,
        approve=False,
    ) == 1

    assert usage_count(path) == 0


def test_unauthorized_gateway_does_not_consume_quota(
    environment,
):

    client, path = environment

    response = client.post(
        "/api/v1/inference",
        json=VALID_REQUEST,
        headers={
            "x-aegis-gateway-token": "invalid"
        },
    )

    assert response.status_code == 403

    assert usage_count(path) == 0


def test_database_failure_blocks_api_and_cli(
    environment,
    monkeypatch,
):

    client, path = environment

    path.chmod(0o644)

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        response = client.post(
            "/api/v1/inference",
            json=VALID_REQUEST,
        )

        assert response.status_code == 503

        assert invoke_cli(monkeypatch) == 1

        provider.return_value.complete.assert_not_called()


def test_provider_failure_consumes_quota(
    environment,
):

    client, path = environment

    with patch(
        "aegis.services.inference.GeminiProvider"
    ) as provider:

        provider.return_value.complete.side_effect = (
            RuntimeError("Synthetic provider failure")
        )

        response = client.post(
            "/api/v1/inference",
            json=VALID_REQUEST,
        )

        assert response.status_code == 503

        assert usage_count(path) == 1
