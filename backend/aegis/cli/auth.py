import argparse
import getpass
import sqlite3
import sys
import warnings

from aegis.security.owner import (
    create_owner,
    owner_exists,
    reset_owner_password,
    OwnerAlreadyExists,
    OwnerNotConfigured,
    InvalidUsername,
)

from aegis.security.passwords import InvalidPassword


def read_password() -> str:

    with warnings.catch_warnings():

        warnings.simplefilter(
            "error",
            getpass.GetPassWarning,
        )

        password = getpass.getpass("Password: ")

        confirmation = getpass.getpass(
            "Confirm password: "
        )

    if password != confirmation:

        raise InvalidPassword(
            "Passwords do not match"
        )

    return password


def main():

    parser = argparse.ArgumentParser(
        description="Aegis local owner management"
    )

    parser.add_argument(
        "command",
        choices=[
            "create-owner",
            "reset-password",
            "status",
        ],
    )

    args = parser.parse_args()

    try:

        if args.command == "status":

            if owner_exists():
                print("Owner account: configured")
            else:
                print("Owner account: not configured")

            return 0

        if not sys.stdin.isatty():

            print("Interactive terminal required.")
            return 1

        if args.command == "create-owner":

            if owner_exists():

                print("An owner account already exists.")
                return 1

            username = input("Username: ")
            password = read_password()

            create_owner(username, password)

            print("Owner account created successfully.")

            return 0

        if args.command == "reset-password":

            if not owner_exists():

                print("Owner account is not configured.")
                return 1

            print(
                "Password recovery will revoke all "
                "existing sessions."
            )

            confirmation = input(
                "Type RESET to continue: "
            )

            if confirmation != "RESET":

                print("Operation cancelled.")
                return 1

            password = read_password()

            reset_owner_password(password)

            print("Owner password reset successfully.")
            print("All previous sessions revoked.")

            return 0

    except (
        InvalidUsername,
        InvalidPassword,
        OwnerAlreadyExists,
        OwnerNotConfigured,
    ) as error:

        print(str(error))
        return 1

    except (KeyboardInterrupt, EOFError):

        print("\nOperation cancelled.")
        return 1

    except (
        sqlite3.Error,
        OSError,
        getpass.GetPassWarning,
    ):

        print("Secure owner operation unavailable.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
