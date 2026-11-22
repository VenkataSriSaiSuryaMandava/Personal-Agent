import getpass
import sys
import warnings

from unittest.mock import Mock

import pytest

from aegis.cli import auth


PASSWORD = "Synthetic CLI password 2026!"


@pytest.fixture
def cli(monkeypatch):

    create = Mock()
    reset = Mock()
    exists = Mock(return_value=False)

    monkeypatch.setattr(auth, "create_owner", create)

    monkeypatch.setattr(
        auth,
        "reset_owner_password",
        reset,
    )

    monkeypatch.setattr(auth, "owner_exists", exists)

    monkeypatch.setattr(
        sys.stdin,
        "isatty",
        lambda: True,
    )

    return create, reset, exists


def command(monkeypatch, name):

    monkeypatch.setattr(
        sys,
        "argv",
        ["auth", name],
    )


def test_unconfigured_status(cli, monkeypatch, capsys):

    command(monkeypatch, "status")

    assert auth.main() == 0

    assert "not configured" in capsys.readouterr().out


def test_configured_status(cli, monkeypatch, capsys):

    _, _, exists = cli

    exists.return_value = True

    command(monkeypatch, "status")

    assert auth.main() == 0

    assert "Owner account: configured" in (
        capsys.readouterr().out
    )


def test_create_owner(cli, monkeypatch):

    create, _, _ = cli

    command(monkeypatch, "create-owner")

    monkeypatch.setattr(
        "builtins.input",
        lambda _: "test-owner",
    )

    monkeypatch.setattr(
        getpass,
        "getpass",
        lambda _: PASSWORD,
    )

    assert auth.main() == 0

    create.assert_called_once_with(
        "test-owner",
        PASSWORD,
    )


def test_duplicate_owner_rejected(cli, monkeypatch):

    create, _, exists = cli

    exists.return_value = True

    command(monkeypatch, "create-owner")

    assert auth.main() == 1

    create.assert_not_called()


def test_noninteractive_creation_rejected(
    cli,
    monkeypatch,
):

    create, _, _ = cli

    command(monkeypatch, "create-owner")

    monkeypatch.setattr(
        sys.stdin,
        "isatty",
        lambda: False,
    )

    assert auth.main() == 1

    create.assert_not_called()


def test_password_mismatch(cli, monkeypatch):

    create, _, _ = cli

    command(monkeypatch, "create-owner")

    monkeypatch.setattr(
        "builtins.input",
        lambda _: "test-owner",
    )

    passwords = iter([
        PASSWORD,
        "Different synthetic password",
    ])

    monkeypatch.setattr(
        getpass,
        "getpass",
        lambda _: next(passwords),
    )

    assert auth.main() == 1

    create.assert_not_called()


def test_password_reset(cli, monkeypatch):

    _, reset, exists = cli

    exists.return_value = True

    command(monkeypatch, "reset-password")

    monkeypatch.setattr(
        "builtins.input",
        lambda _: "RESET",
    )

    monkeypatch.setattr(
        getpass,
        "getpass",
        lambda _: PASSWORD,
    )

    assert auth.main() == 0

    reset.assert_called_once_with(PASSWORD)


def test_reset_confirmation_required(
    cli,
    monkeypatch,
):

    _, reset, exists = cli

    exists.return_value = True

    command(monkeypatch, "reset-password")

    monkeypatch.setattr(
        "builtins.input",
        lambda _: "cancel",
    )

    assert auth.main() == 1

    reset.assert_not_called()


def test_reset_requires_owner(cli, monkeypatch):

    _, reset, _ = cli

    command(monkeypatch, "reset-password")

    assert auth.main() == 1

    reset.assert_not_called()


def test_noninteractive_reset_rejected(
    cli,
    monkeypatch,
):

    _, reset, exists = cli

    exists.return_value = True

    command(monkeypatch, "reset-password")

    monkeypatch.setattr(
        sys.stdin,
        "isatty",
        lambda: False,
    )

    assert auth.main() == 1

    reset.assert_not_called()


def test_hidden_password_failure(cli, monkeypatch):

    create, _, _ = cli

    command(monkeypatch, "create-owner")

    monkeypatch.setattr(
        "builtins.input",
        lambda _: "test-owner",
    )

    def insecure_prompt(_):

        warnings.warn(
            "Cannot hide password input",
            getpass.GetPassWarning,
        )

        return PASSWORD

    monkeypatch.setattr(
        getpass,
        "getpass",
        insecure_prompt,
    )

    assert auth.main() == 1

    create.assert_not_called()


def test_password_not_printed(
    cli,
    monkeypatch,
    capsys,
):

    command(monkeypatch, "create-owner")

    monkeypatch.setattr(
        "builtins.input",
        lambda _: "test-owner",
    )

    monkeypatch.setattr(
        getpass,
        "getpass",
        lambda _: PASSWORD,
    )

    assert auth.main() == 0

    captured = capsys.readouterr()

    assert PASSWORD not in captured.out
    assert PASSWORD not in captured.err
